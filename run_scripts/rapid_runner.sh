#!/bin/bash

# Set the path to the folder containing the input files
input_folder="/home/user/rapid/examples/list-examples/list-simple/"

# Set the path to the folder where the output files will be saved
output_folder="/home/user/rapid_output5/"

# Set the executable command and its arguments
executable_command="/home/user/rapid/build-fresh/bin/rapid"
command_arguments=" -integerIterations on -vampViaFile on -genInvariants on "

# Iterate over each file in the input folder
for file in "$input_folder"/*; do
    # Check if the current item is a file
    if [ -f "$file" ]; then
        # Extract the file name (without extension)
        file_name=$(basename "$file")
        file_name="${file_name%.*}"

        # Define the output file path
        output_file="$output_folder/$file_name.txt"

        # Run the executable command with arguments on the current file
        time timeout -s SIGKILL 900s $executable_command $command_arguments "$file" > "$output_file"

        # Print a message indicating the completion of processing for the current file
        echo "Processed $file"
    fi
done

