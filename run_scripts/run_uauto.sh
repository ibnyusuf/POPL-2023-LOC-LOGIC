#!/bin/bash

HERE=$(pwd)

find ~/c-files/list-simple/* -name *.c | while read line 
do
  echo $line
  path=$(echo $line | cut -d'/' -f5-)
  echo $path
  mkdir -p $path
  cd $path
  ln -s /home/vm/UAutomizer-linux/z3 z3
  ln -s /home/vm/UAutomizer-linux/cvc4 cvc4
  ln -s /home/vm/UAutomizer-linux/mathsat mathsat
  time timeout -s SIGKILL 900s ~/UAutomizer-linux/Ultimate.py --spec ~/unreach-call.prp --file $line --architecture 32bit &> OUT 
  cd $HERE
done
