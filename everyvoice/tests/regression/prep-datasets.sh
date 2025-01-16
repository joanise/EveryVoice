#!/bin/bash

# Prepare the datasets and directories for our regression test cases

set -o errexit

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

EVERYVOICE_REGRESS_ROOT=$(python -c 'import everyvoice; print(everyvoice.__path__[0])')/tests/regression

LJ_SPEECH_DATASET=$HOME/sgile/data/LJSpeech-1.1
LJSLICES="150 600 1600 full"
for slice in $LJSLICES; do
    dir=regress-lj-$slice
    mkdir "$dir"
    ln -s "$LJ_SPEECH_DATASET/wavs" "$dir"/
    get_slice "$slice" < "$LJ_SPEECH_DATASET/metadata.csv" > "$dir"/metadata.csv
    cp "$EVERYVOICE_REGRESS_ROOT"/wizard-resume-lj "$dir"/wizard-resume
    cp "$EVERYVOICE_REGRESS_ROOT"/test-lj.txt "$dir"/test.txt
    cp "$EVERYVOICE_REGRESS_ROOT"/test2-lj.txt "$dir"/test2.txt
done

SinhalaTTS=$HOME/sgile/data/SinhalaTTS
dir=regress-si
mkdir $dir
ln -s "$SinhalaTTS/wavs" $dir/
cp "$SinhalaTTS/si_lk.lines.txt" $dir/
cp "$EVERYVOICE_REGRESS_ROOT"/wizard-resume-si "$dir"/wizard-resume
cp "$EVERYVOICE_REGRESS_ROOT"/test-si.txt "$dir"/test.txt
cp "$EVERYVOICE_REGRESS_ROOT"/test2-si.txt "$dir"/test2.txt

isiXhosa=$HOME/sgile/data/OpenSLR32-four-South-Afican-languages/xh_za/za/xho
dir=regress-xh
mkdir $dir
ln -s "$isiXhosa/wavs" $dir/
cp "$isiXhosa/line_index.tsv" $dir/
cp "$EVERYVOICE_REGRESS_ROOT"/wizard-resume-xh "$dir"/wizard-resume
cp "$EVERYVOICE_REGRESS_ROOT"/test-xh.txt "$dir"/test.txt
cp "$EVERYVOICE_REGRESS_ROOT"/test2-xh.txt "$dir"/test2.txt
