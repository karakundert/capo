#! /bin/bash

mysql < killDB.sql
mysql < createDB.sql
./initDB.py
./add_host.py GrumpyCat 127.0.0.1 damo 
./new_observation.py GrumpyCat `ls -d test_files/*`
./md5update.py test_files/*
