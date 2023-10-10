use fast_matcher::{Args, start};
use clap::Parser;

fn main() {
    let args = Args::parse();
    start(args);
}