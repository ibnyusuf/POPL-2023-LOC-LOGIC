#!/bin/bash

HERE=$(pwd)

find ~/c-files/list-simple/* -name *.c | while read line 
do
  echo $line
  path=$(echo $line | cut -d'/' -f5-)
  echo $path
  mkdir -p $path
  cd $path
  time timeout -s SIGKILL 900s ~/symbiotic/bin/symbiotic --witness witness.graphml --sv-comp  --prp=assert $line &> OUT 
  cd $HERE
done
