# EveryVoice regression test suite

## Preparing the regression training data:

 - Download LJ 1.1 from https://keithito.com/LJ-Speech-Dataset/
 - Download Sinhala TTS from https://openslr.org/30/
 - Download High quality TTS data for four South African languages (af, st, tn,
   xh) from https://openslr.org/32
 - See [`prep-datasets.sh`](prep-datasets.sh) to see where these datasets are expected to be found.
 - Run this to create the regression testing directory structure:

       mkdir regress-1  # or any suffix you want
       cd regress-1
       ../prep-datasets.sh

## Running the regression tests

On a Slurm cluster:

    for dir in regress-*; do
        pushd $dir
        sbatch ../../regression-test.sh
        popd
    done

Or just use `../../regression-test.sh` directly in the loop if you're not on a cluster.

## Test data provenance

 - `test-si.txt`: copied from https://en.wikipedia.org/wiki/Sinhala_script CC BY-SA-4.0
    - the first line means Sinhala script, found at the top of the page
    - the rest is the first verse from the Pali Dhammapada lower on the same page
 - `test2-si.txt`: one word from that first line

 - `test*-xh.txt`: individual words copied from https://en.wikipedia.org/wiki/Xhosa_language
   CC BY-SA-4.0

 - `test*-lj.txt`: written by Eric Joanis
