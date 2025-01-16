#!/bin/bash

# Prepare the datasets and directories for our regression test cases

set -o errexit

LJ_SPEECH_DATASET=$HOME/sgile/data/LJSpeech-1.1
LJSLICES="150 600 1600 full"

# Usage: cat my_file | get_slice lines_to_keep > out
# Use a number of lines or full to get all lines
get_slice() {
    lines=$1
    if [[ $lines == full ]]; then
        cat
    else
        head -"$lines"
    fi
}

for slice in $LJSLICES; do
    dir=regress-lj-$slice
    mkdir "$dir"
    ln -s "$LJ_SPEECH_DATASET/wavs" "$dir"/
    get_slice "$slice" < "$LJ_SPEECH_DATASET/metadata.csv" > "$dir"/metadata.csv
done

SinhalaTTS=$HOME/sgile/data/SinhalaTTS
dir=regress-si
mkdir $dir
ln -s "$SinhalaTTS/wavs" $dir/
cp "$SinhalaTTS/si_lk.lines.txt" $dir/

isiXhosa=$HOME/sgile/data/OpenSLR32-four-South-Afican-languages/xh_za/za/xho
dir=regress-xh
mkdir $dir
ln -s "$isiXhosa/wavs" $dir/
cp "$isiXhosa/line_index.tsv" $dir/
