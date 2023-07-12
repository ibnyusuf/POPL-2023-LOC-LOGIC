#!/bin/bash

CONFIG=~/CPAchecker-2.2-unix/config/svcomp23.properties
SPEC=~/CPAchecker-2.2-unix/config/specification/sv-comp-reachability.spc

HERE=$(pwd)

find ~/c-files/* -name *.c | while read line 
do
  echo $line
  path=$(echo $line | cut -d'/' -f5-)
  echo $path
  mkdir -p $path
  cd $path
  time ~/CPAchecker-2.2-unix/scripts/cpa.sh -timelimit 900s -config $CONFIG -spec $SPEC -preprocess $line &> OUT 
  cd $HERE
done
