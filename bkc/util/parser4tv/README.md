# parser4tv 
This tool takes an addr2line type of kAFL trace dump and outputs a JSON that adheres to the [Trace Event Format](https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview)  for utilizing the trace visualization from [Catapult](https://chromium.googlesource.com/catapult/+/HEAD/README.md) [Trace-viewer](https://chromium.googlesource.com/catapult/+/HEAD/tracing/README.md), and 'parser4tv' stands for Parser For Trace-Viewer.

## Usage
See usage by executing the `parser4tv.py` script.

The tool requires an address 2 line trace list as the main input with the following options:\
`-o`, `--output_name`, specify the output name. default: trace_out.json or _f[#].lst in `-e` mode\
`-e`, `--extract_lines`, extract first N line of traces to a separate trace list\
`-s`, `--stop_at`, hint the parser to stop processing after N lines.
`--time_interval` set time interval for the basic unit, default = 10 us. This helps resize the default visual granularity.\
`-f`, `--force_overwrite`, force overwrite existing output files\
`-v` enable verbose mode\
`--task_view` **experimental feature:** try to infer context switch to differentiate tasks from the trace.\
`--readable_json` enable layered JSON, for a more human-readable format


## Example
See a [example](../../../docs/example_parser4tv.md) for more detail.


## Caveat & potential TODOs
The parser4tv script has the following limitations and plans for improvement. 
1. Improve `--task_view` accuracy.  See more from the [example](../../../docs/example_parser4tv.md#experiemental-feature---task_view).
2. Integrate other insights into the view.
3. Provide more trace sanitization checks for malformed entries.
4. Improve the [step](../../../docs/example_parser4tv.md#generate-trace-dump) of kAFL trace dump
5. Improve `-e` mode with more flexible slicing.
6. Substitute some viewer legends making them more meaningful in the display.