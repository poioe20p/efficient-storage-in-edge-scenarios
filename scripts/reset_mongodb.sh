#!/bin/bash

docker container rm -f mongodb
docker container rm -f mongodb-data
docker volume rm -f mongodb mongodb-data
docker volume rm -f mongodb mongodb