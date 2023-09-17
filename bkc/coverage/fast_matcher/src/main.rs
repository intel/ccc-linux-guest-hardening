/**
 *
 * Copyright (C)  2022  Intel Corporation.
 *
 * This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
 * This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
 *
 * SPDX-License-Identifier: MIT
**/
use addr2line::fallible_iterator::FallibleIterator;
use clap::Parser;
use glob::glob;
use itertools::sorted;
use lzzzz::lz4f::ReadDecompressor;
use rangemap::RangeInclusiveSet;
use regex::Regex;
use std::collections::{HashMap, HashSet};
use std::path::Component;
use std::process::{exit, Command};
use std::thread;
use std::{
    fmt,
    fs::File,
    io,
    io::prelude::*,
    path::{Path, PathBuf},
    sync::{Arc, RwLock},
};
use workctl::WorkQueue;

type Node = u64;
type Edge = (Node, Node);
type Function = String;

type SmatchData = HashMap<LineInfo, Function>;
type SmatchHits = HashSet<LineInfo>;

const PT_TOKEN: Node = 0xffffffffffffffff;

#[derive(Debug, Eq, PartialEq, Hash, Clone, PartialOrd, Ord)]
struct LineInfo {
    path: PathBuf,
    line: u32,
}

impl LineInfo {
    fn new(path: &Path, line: u32) -> Self {
        Self {
            path: normalize(path),
            line,
        }
    }
}

impl fmt::Display for LineInfo {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "{}:{}", self.path.display(), self.line)
    }
}

impl<'a> From<addr2line::Location<'a>> for LineInfo {
    fn from(location: addr2line::Location) -> Self {
        let path = Path::new(location.file.unwrap());
        let line = location.line.unwrap();
        LineInfo::new(path, line)
    }
}

impl From<String> for LineInfo {
    fn from(location: String) -> Self {
        let split: Vec<&str> = location.split(':').collect();
        let path = Path::new(split[0]);
        let line = split[1].parse().unwrap();
        LineInfo::new(path, line)
    }
}

// Stolen from https://github.com/rust-lang/rfcs/issues/2208#issuecomment-342679694
fn normalize(p: &Path) -> PathBuf {
    let mut stack: Vec<Component> = vec![];

    // We assume .components() removes redundant consecutive path separators.
    // Note that .components() also does some normalization of '.' on its own anyways.
    // This '.' normalization happens to be compatible with the approach below.
    for component in p.components() {
        match component {
            // Drop CurDir components, do not even push onto the stack.
            Component::CurDir => {}

            // For ParentDir components, we need to use the contents of the stack.
            Component::ParentDir => {
                // Look at the top element of stack, if any.
                let top = stack.last().cloned();

                match top {
                    // A component is on the stack, need more pattern matching.
                    Some(c) => {
                        match c {
                            // Push the ParentDir on the stack.
                            Component::Prefix(_) => {
                                stack.push(component);
                            }

                            // The parent of a RootDir is itself, so drop the ParentDir (no-op).
                            Component::RootDir => {}

                            // A CurDir should never be found on the stack, since they are dropped when seen.
                            Component::CurDir => {
                                unreachable!();
                            }

                            // If a ParentDir is found, it must be due to it piling up at the start of a path.
                            // Push the new ParentDir onto the stack.
                            Component::ParentDir => {
                                stack.push(component);
                            }

                            // If a Normal is found, pop it off.
                            Component::Normal(_) => {
                                let _ = stack.pop();
                            }
                        }
                    }

                    // Stack is empty, so path is empty, just push.
                    None => {
                        stack.push(component);
                    }
                }
            }

            // All others, simply push onto the stack.
            _ => {
                stack.push(component);
            }
        }
    }

    // If an empty PathBuf would be return, instead return CurDir ('.').
    if stack.is_empty() {
        let mut path = PathBuf::new();
        path.push(Component::CurDir);
        return path;
    }

    let mut norm_path = PathBuf::new();

    for item in &stack {
        norm_path.push(item);
    }

    norm_path
}

//#[derive(Debug)]
struct TraceFileIter<'a> {
    lines: std::io::Lines<std::io::BufReader<ReadDecompressor<'a, &'a mut File>>>,
}

impl<'a> TraceFileIter<'a> {
    fn new(file: &'a mut File) -> Result<Self, io::Error> {
        //let mut file = File::open(fname)?;
        let reader = ReadDecompressor::new(file)?;
        //let re = Regex::new(r"([\d+a-f]+),([\d+a-f]+)").unwrap();
        //let br = LineReader::new(file)?;
        let br = io::BufReader::new(reader);
        let lines = br.lines();
        //let res = Self{re, lines: lines};
        let res = Self { lines };

        Ok(res)
    }
}

impl<'a> Iterator for TraceFileIter<'a> {
    type Item = Edge;

    fn next(&mut self) -> Option<Self::Item> {
        if let Some(Ok(next)) = self.lines.next() {
            let d: Vec<&str> = next.trim_end().split(',').collect();
            if d.len() != 2 {
                // ptdump timeout may lead to partly written files..
                eprintln!(
                    "Failed to parse trace, line input \"{}\" - skipping..",
                    next
                );
                return None;
            }
            let src = match u64::from_str_radix(d[0], 16) {
                Ok(src) => src,
                Err(e) => panic!("Failed to parse line input \"{}\": {}", next, e),
            };
            let dst = match u64::from_str_radix(d[1], 16) {
                Ok(dst) => dst,
                Err(e) => panic!("Failed to parse line input \"{}\": {}", next, e),
            };
            // Filter out PT_TOKEN edges
            if dst == PT_TOKEN {
                if let Some((src_next, dst_next)) = self.next() {
                    if src_next == PT_TOKEN {
                        return Some((src, dst_next));
                    } else {
                        panic!("unexpected PT_TOKEN in trace");
                    }
                }
            }
            return Some((src, dst));
        }

        None
    }
}

#[allow(dead_code)]
fn read_trace_file(fname: &Path, nodes_collector: &mut HashSet<Node>) -> Result<(), io::Error> {
    let mut f = File::open(fname).unwrap();
    let ti = TraceFileIter::new(&mut f).unwrap();
    for edge in ti {
        //println!("{:?}", edge);
        nodes_collector.insert(edge.0);
        nodes_collector.insert(edge.1);
    }
    Ok(())
}

#[allow(dead_code)]
fn get_addr_func<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    addr: Node,
) -> Option<Function> {
    // Avoid overflow in find_location()
    if addr == PT_TOKEN {
        return None;
    }
    let mut frames = ctx.find_frames(addr).skip_all_loads().unwrap();
    while let Some(frame) = frames.next().unwrap() {
        if let Some(func) = frame.function {
            let func_name = func.raw_name().unwrap();
            return Some(func_name.to_string());
        }
    }

    None
}

#[allow(dead_code)]
fn get_addr_frame_func<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    addr: Node,
) -> Option<Function> {
    // Avoid overflow in find_location()
    if addr == PT_TOKEN {
        return None;
    }
    let frames = ctx.find_frames(addr).skip_all_loads().unwrap();
    if let Some(frame) = frames.last().unwrap() {
        if let Some(func) = frame.function {
            let func_name = func.raw_name().unwrap();
            return Some(func_name.to_string());
        }
    }

    None
}

#[allow(dead_code)]
fn get_addr_funcs<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    addr: Node,
) -> Vec<(Function, LineInfo)> {
    // Avoid overflow in find_location()
    let mut result = Vec::new();
    if addr == PT_TOKEN {
        return result;
    }
    let mut frames = ctx.find_frames(addr).skip_all_loads().unwrap();
    while let Some(frame) = frames.next().unwrap() {
        if let Some(func) = frame.function {
            let func_name = func.raw_name().unwrap();
            let lineinfo = LineInfo::from(frame.location.unwrap());
            result.push((func_name.to_string(), lineinfo));
        }
    }

    result
}

#[allow(dead_code)]
fn get_addr_frame_lineinfo<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    addr: Node,
    prefix: &Path,
) -> Option<LineInfo> {
    // Avoid overflow in find_location()
    if addr == PT_TOKEN {
        return None;
    }
    let frames = ctx.find_frames(addr).skip_all_loads().unwrap();
    if let Some(frame) = frames.last().unwrap() {
        if let Some(l) = frame.location {
            let file = l.file.unwrap();
            let line = l.line.unwrap();
            let f_path = Path::new(file);
            let path = f_path.strip_prefix(prefix).unwrap_or(f_path);
            //let lineinfo = LineInfo::from(frame.location.unwrap());
            let lineinfo = LineInfo::new(path, line);
            return Some(lineinfo);
        }
    }

    None
}

#[allow(dead_code)]
fn get_addr_frame_lineinfos<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    addr: Node,
    prefix: &Path,
) -> HashSet<LineInfo> {
    // Avoid overflow in find_location()
    let mut result = HashSet::new();
    if addr == PT_TOKEN {
        return result;
    }
    let mut frames = ctx.find_frames(addr).skip_all_loads().unwrap();
    while let Some(frame) = frames.next().unwrap() {
        if let Some(l) = frame.location {
            let file = l.file.unwrap();
            let line = l.line.unwrap();
            let f_path = Path::new(file);
            let path = f_path.strip_prefix(prefix).unwrap_or(f_path);
            //let lineinfo = LineInfo::from(frame.location.unwrap());
            let lineinfo = LineInfo::new(path, line);
            result.insert(lineinfo);
        }
    }

    result
}

#[allow(dead_code)]
fn get_addr_lineinfo<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    addr: Node,
    prefix: &Path,
) -> Option<LineInfo> {
    // Avoid overflow in find_location()
    if addr == PT_TOKEN {
        return None;
    }
    if let Some(l) = ctx.find_location(addr).unwrap() {
        let file = l.file.unwrap();
        let line = l.line.unwrap();
        let f_path = Path::new(file);
        let path = f_path.strip_prefix(prefix).unwrap_or(f_path);
        //println!("{}:{}", path.display(), line);
        let lineinfo = LineInfo::new(path, line);
        return Some(lineinfo);
    }
    None
}

#[allow(dead_code)]
fn get_addr_lineinfo_range<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    start: Node,
    end: Node,
    prefix: &Path,
    include_frames: bool,
) -> Vec<LineInfo> {
    let infos = ctx.find_location_range(start, end).unwrap();
    let mut result = Vec::new();
    for (s, _e, l) in infos {
        let file = l.file.unwrap();
        let line = l.line.unwrap();
        let f_path = Path::new(file);
        let path = f_path.strip_prefix(prefix).unwrap_or(f_path);
        //println!("{}:{}", path.display(), line);
        let lineinfo = LineInfo::new(path, line);
        result.push(lineinfo);
        if include_frames {
            let frame_lines = get_addr_frame_lineinfos(ctx, s, prefix);
            result.extend(frame_lines);
        }
    }
    result
}

#[allow(dead_code)]
fn in_same_function<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    _smatch_funcs: &HashSet<Function>,
    a: Node,
    b: Node,
) -> bool {
    //fn in_same_function_and_is_smatch_func<R: addr2line::gimli::Reader>(ctx: &addr2line::Context<R>, smatch_funcs: &HashSet<Function>, a: Node, b: Node) -> bool{
    if let Some(cur_func) = get_addr_func(ctx, a) {
        if let Some(prev_func) = get_addr_func(ctx, b) {
            // Optimization
            //if smatch_funcs.contains(&prev_func) {
            return cur_func == prev_func;
            //}
        }
    }
    false
}

#[allow(dead_code)]
fn in_same_frame_function<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    _smatch_funcs: &HashSet<Function>,
    a: Node,
    b: Node,
) -> bool {
    if let Some(cur_func) = get_addr_frame_func(ctx, a) {
        if let Some(prev_func) = get_addr_frame_func(ctx, b) {
            return cur_func == prev_func;
        }
    }
    false
}

fn read_trace_file_get_ranges<R: addr2line::gimli::Reader>(
    ctx: &addr2line::Context<R>,
    trace_file: &Path,
    smatch_data: &SmatchData,
) -> Result<RangeInclusiveSet<Node>, io::Error> {
    let mut f = File::open(trace_file).unwrap();
    let ti = TraceFileIter::new(&mut f).unwrap();
    let mut ranges = RangeInclusiveSet::new();
    let smatch_funcs: HashSet<Function> = smatch_data.values().cloned().collect();

    let mut prev_edge: Option<Edge> = None;
    for edge in ti {
        // Trace:
        // ...
        // (prev_src, prev_dst)
        // (src, dst)
        // ...
        // Get code pointer ranges between prev_dst and src

        let src = edge.0;
        let dst = edge.1;

        if let Some(prev) = prev_edge {
            let prev_dst = prev.1;

            // 1. range match for '[prev_dst, src]'
            // Only get range of lines if prev_dst and src are in same function (match against all frame funcs)
            // and if the range has not been resolved before

            // Get possible functions (i.e., inlining sequence) for prev_dst and src
            let frame_funcs = get_addr_funcs(ctx, prev_dst);
            let frame_funcs_2 = get_addr_funcs(ctx, src);
            let s1: HashSet<Function> = frame_funcs.iter().map(|(f, _l)| f.to_string()).collect();
            let s2: HashSet<Function> = frame_funcs_2.iter().map(|(f, _l)| f.to_string()).collect();
            let is: HashSet<Function> = s1.intersection(&s2).map(|s| s.to_string()).collect();
            let func_intersect_len = is.intersection(&smatch_funcs).count();
            //let mut func_intersect_len = s1.intersection(&smatch_funcs).count();
            //func_intersect_len += s2.intersection(&smatch_funcs).count();

            if prev_dst <= src && func_intersect_len > 0 {
                ranges.insert(prev_dst..=src);
            }
        }
        // Insert src and dst, just to be sure
        // TODO: check if earlier ranges will be inclusive
        ranges.insert(src..=src);
        ranges.insert(dst..=dst);

        // Store edge
        prev_edge = Some(edge);
    }
    Ok(ranges)
}

fn collect_smatch_report(fname: &Path) -> Result<SmatchData, io::Error> {
    let mut f = File::open(fname)?;
    let mut s = String::new();
    f.read_to_string(&mut s)?;

    let re = Regex::new(r"(\S+:[0-9]+)\s(\S+)\(\)").unwrap();
    //let re_warn_error = Regex::new(r".*(warn:\|error:).*").unwrap();
    let smatch_data: SmatchData = re
        .captures_iter(&s)
        .map(|cap| {
            let line = cap.get(1).unwrap().as_str().to_string();
            let func = cap.get(2).unwrap().as_str().to_string();
            let lineinfo = LineInfo::from(line);
            (lineinfo, func)
        })
        .collect();

    Ok(smatch_data)
}

#[allow(dead_code)]
fn match_smatch_report(fname: &Path, hits: SmatchHits) -> Result<(), io::Error> {
    let f = File::open(fname)?;

    let br = io::BufReader::new(f);
    // Match fileinfo
    let re = Regex::new(r"(\S+:[0-9]+)").unwrap();
    br.lines().for_each(|report_line| {
        if let Ok(l) = report_line {
            for cap in re.captures_iter(&l) {
                let line = LineInfo::from(cap.get(1).unwrap().as_str().to_string());
                if hits.contains(&line) {
                    println!("{}", l);
                }
            }
        }
    });

    Ok(())
}

fn string_to_static_str(s: String) -> &'static str {
    Box::leak(s.into_boxed_str())
}

// Hack
// TODO: write btter implementation that reads this from DWARF
fn get_linux_source_path(vmlinux_path: &Path) -> Option<String> {
    let cmd = format!(
        "readelf --debug-dump=info {} | grep DW_AT_comp_dir | head -n 1 | cut -d: -f 4 | xargs",
        vmlinux_path.display()
    );
    let output = Command::new("/usr/bin/bash")
        .arg("-c")
        .arg(cmd)
        .output()
        .expect("failed to execute process");

    if !output.status.success() {
        eprintln!("Failed obtaining source dir prefix. Please set --prefix to location of your linux build dir to strip debug info absolute path prefix. readelf output: '{}'", String::from_utf8_lossy(&output.stderr));
        return None;
    }

    let path = unsafe {
        String::from_utf8_unchecked(output.stdout)
            .trim()
            .to_string()
    };

    Some(path)
}

fn assert_file_exists(path: &Path) {
    if !path.is_file() {
        eprintln!(
            "file '{}' does not exist! Please provide a valid file.",
            path.display()
        );
        exit(1);
    }
}

fn do_checks(traces_dir: &Path, smatch_report: &Path, vmlinux_path: &Path) {
    if !traces_dir.is_dir() {
        eprintln!(
            "Could not find traces dir '{}'. Please generate the traces with 'fuzz.sh cov'.",
            traces_dir.display()
        );
        exit(1);
    }
    assert_file_exists(smatch_report);
    assert_file_exists(vmlinux_path);
}

fn populate_wq(wq: &mut WorkQueue<PathBuf>, traces_dir: &Path) {
    let trace_dir_str = traces_dir.to_str().unwrap().to_owned();
    glob(&(trace_dir_str.clone() + "/fuzz*.lst.lz4"))
        .expect("Failed to read glob pattern")
        .for_each(|entry| {
            if let Ok(path) = entry {
                eprintln!("Push: {:?}", path.display());
                wq.push_work(path);
            }
        });

    // Support legacy trace paths
    glob(&(trace_dir_str + "/payload_*.lz4"))
        .expect("Failed to read glob pattern")
        .for_each(|entry| {
            if let Ok(path) = entry {
                eprintln!("Push: {:?}", path.display());
                wq.push_work(path);
            }
        });
}

fn start(args: Args) {
    let nproc = args.parallelize;

    let workdir = Path::new(&args.workdir);
    if !workdir.is_dir() {
        eprintln!("Could not find workdir dir '{}'.", workdir.display());
        exit(1);
    }
    eprintln!("The workdir passed is: {:?}", workdir);
    let traces_dir = workdir.join("traces");
    let vmlinux_path = workdir.join("target").join("vmlinux");

    let smatch_report = match args.smatch_report {
        Some(f) => f,
        None => workdir.join("target").join("smatch_warns.txt"),
    };

    let smatch_entries = collect_smatch_report(&smatch_report).unwrap();

    // Get kernel source dir prefix, so we can strip the absolute path later
    let prefix = Path::new(string_to_static_str(match args.prefix {
        Some(f) => f,
        None => get_linux_source_path(&vmlinux_path).unwrap(),
    }));

    // Sanity checks
    do_checks(&traces_dir, &smatch_report, &vmlinux_path);

    // Parallelize stuff
    let mut threads = Vec::new();
    let mut wq = WorkQueue::new();

    populate_wq(&mut wq, &traces_dir);

    let ranges_db = Arc::new(RwLock::new(RangeInclusiveSet::new()));

    for _i in 0..nproc {
        let smatch_entries = smatch_entries.clone();
        let ranges_db = ranges_db.clone();
        let mut thread_wq = wq.clone();

        let fdebug = File::open(&vmlinux_path).unwrap();
        let map = unsafe { memmap::Mmap::map(&fdebug).unwrap() };

        let t = thread::spawn(move || {
            let addr2line_file = addr2line::object::File::parse(&*map).unwrap();
            let a2l = addr2line::Context::new(&addr2line_file).unwrap();
            while let Some(path) = thread_wq.pull_work() {
                eprintln!("Processing: {:?}", path.display());
                if let Ok(res) = read_trace_file_get_ranges(&a2l, &path, &smatch_entries) {
                    if let Ok(mut db) = ranges_db.write() {
                        for range in res {
                            db.insert(range);
                        }
                    }
                }
            }
        });
        threads.push(t);
    }

    for t in threads {
        t.join().ok();
    }
    eprintln!("Done parsing traces... Now finding reached lines.");

    if let Ok(ranges) = ranges_db.read() {
        let fdebug = File::open(&vmlinux_path).unwrap();
        let map = unsafe { memmap::Mmap::map(&fdebug).unwrap() };
        let addr2line_file = addr2line::object::File::parse(&*map).unwrap();
        let a2l = addr2line::Context::new(&addr2line_file).unwrap();

        let mut hits = HashSet::new();
        for range in ranges.iter() {
            // Collect range info
            //eprintln!("range {:x} - {:x} ({} bytes)", *range.start(), *range.end(), *range.end() - *range.start());
            let lineinfos =
                get_addr_lineinfo_range(&a2l, *range.start(), *range.end(), prefix, args.frames);

            for info in lineinfos {
                if smatch_entries.contains_key(&info) || args.all_visited {
                    hits.insert(info);
                }
            }
        }
        // Print hit lines if not invoked --match
        if !args.match_only {
            for hit in sorted(hits.clone()) {
                println!("{}", hit)
            }
        }

        // If invoked with --match, print the lines from the smatch report
        if args.match_only {
            match_smatch_report(&smatch_report, hits.clone()).ok();
        }
        eprintln!(
            "FOUND {} matches with {}",
            hits.len(),
            smatch_report.display()
        );
    };
}

#[derive(Parser)]
#[command(
    author,
    version,
    about = "Parse kAFL traces and match them against a Smatch report"
)]
struct Args {
    workdir: PathBuf,
    #[arg(short, long, default_value = "1")]
    parallelize: usize,
    #[arg(short, long)]
    smatch_report: Option<PathBuf>,
    #[arg(short = 'm', long = "match")]
    match_only: bool,
    #[arg(short = 'a', long = "all-visited")]
    all_visited: bool,
    #[arg(short = 'f', long = "frames")]
    frames: bool,
    #[arg(long = "prefix")]
    prefix: Option<String>,
}

fn main() {
    let args = Args::parse();
    start(args);
}
