#!/usr/bin/env bash


# git URL to the Mboshi data repository.
url="https://github.com/besacier/mboshi-french-parallel-corpus.git"


if [ $# -ne 1 ]; then
    echo "usage: $0 <out-datadir>"
    exit 1
fi

datadir=$1


# Download the data.
if [ ! -d $datadir/local/mboshi ]; then
    git clone $url $datadir/local/mboshi
else
    echo "Data already downloaded. Skipping."
fi


function scp_line {
    wav=$0
    uttid=$(basename $wav)
    uttid=${uttid%.*}
    echo $uttid $wav
}
export -f scp_line


# Create the uttids/wavs.scp files for each data set.
for x in train dev; do
    mkdir -p $datadir/$x
    find $datadir/local/mboshi/full_corpus_newsplit/$x -name '*wav' \
        -exec bash -c 'scp_line "$0"' {} {} \; \
        | sort | uniq > $datadir/$x/wavs.scp
    cat $datadir/$x/wavs.scp | awk '{print $1}' >$datadir/$x/uttids
done
