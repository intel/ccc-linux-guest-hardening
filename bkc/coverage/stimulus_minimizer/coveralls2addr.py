#!/usr/bin/python3

# 
# Copyright (C)  2022  Intel Corporation. 
#
# This software and the related documents are Intel copyrighted materials, and your use of them is governed by the express license under which they were provided to you ("License"). Unless the License provides otherwise, you may not use, modify, copy, publish, distribute, disclose or transmit this software or the related documents without Intel's prior written permission.
# This software and the related documents are provided as is, with no express or implied warranties, other than those that are expressly stated in the License.
#
# SPDX-License-Identifier: MIT

import json

# parse gcovr coveralls json output
with open('gcovr.json') as json_file:
    report = json.load(json_file)
    #print(repr(report['source_files']))
    for f in report['source_files']:
        #print(f['name'])
        line = 0
        for num in f['coverage']:
            line += 1
            if num and num > 0:
                print("%6d %s:%d" % (num, f['name'],line))
        #for line in f['lines']:
        #    if line['gcovr/noncode']:
        #        print("%s:%d" % (f['file'], line['line_number']))
