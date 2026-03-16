#!/bin/bash
mkdir -p logs data
python dashboard/app.py &
python main_multi.py
