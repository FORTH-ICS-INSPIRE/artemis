#!/bin/sh

for filename in ./*.js; do
    google-closure-compiler --js $filename --js_output_file ./prod/'prod-'$(basename $filename)
done
