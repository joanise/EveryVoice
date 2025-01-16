#!/bin/bash

# Automated application of the instructions in README.md

set -o errexit

TOP_LEVEL_DIR=$(mktemp --directory regress-XXX)
cd "$TOP_LEVEL_DIR"

../prep-datasets.sh
for DIR in regress-*; do
    pushd "$DIR"
    sbatch ../../regression-test.sh
    popd
done

coverage run -p -m everyvoice test

JOB_COUNT=$(find . -maxdepth 1 -name regress-\* | wc -l)
while true; do
    DONE_COUNT=$(find . -maxdepth 2 -name DONE | wc -l)
    if (( DONE_COUNT + 2 >= JOB_COUNT )); then
        break
    fi
    echo "$DONE_COUNT/$JOB_COUNT regression job(s) done. Still waiting."
    date
    sleep $(( 60 * 5 ))
done

echo "$DONE_COUNT regression jobs done. Calculating coverage now, but some jobs may still be running."
../combine-coverage.sh
cat coverage.txt

while true; do
    DONE_COUNT=$(find . -maxdepth 2 -name DONE | wc -l)
    if (( DONE_COUNT >= JOB_COUNT )); then
        break
    fi
    echo "$DONE_COUNT/$JOB_COUNT regression job(s) done. Still waiting."
    date
    sleep $(( 60 * 5 ))
done

echo "All $DONE_COUNT regression jobs done. Calculating final coverage."
rm .coverage
../combine-coverage.sh
cat coverage.txt
