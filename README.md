# Image Processing Back-End app


### Requirements

- python 3.11 
```sh
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11
```

- redis
```sh
sudo apt install redis-server
sudo systemctl start redis
```

- postgresql 15+
```sh
sudo apt install postgresql
sudo systemctl start postgresql
```

### Installation

You can run the script `install.sh` that does everything.


### Starting

You need to start the worker and the API with:
- worker: 
```sh
python run_worker.py worker
```
- API:
```sh
python run_dev.py
```

There is an example `.env` file (`.env.example`) that provide you examples variables that works for developpement, the stripe variables should works too.


## Docker Usage

There is also a conteneurized version of this project using dockerfiles and docker compose to run the multiple services within different service: database, worker, api-server and redis.

First you need to build the 2 images, one for the api-server and one for the worker, the others will be downloaded from dockerhub.
```sh
sudo docker build -t app-build --file Dockerfile .
sudo docker bulid -t app-build-worker --file Dockerfile.worker .
```

Once you got those images built (this might take a while since it hase to setup all thje python libraries), you can start the docker compose with:
```sh
sudo docker compose -f docker-compose-file.yaml up
```
Make sure to change `docker-compose-file.yaml` depending if your host got a GPU or not (`docker-compose.yaml` or `docker-compose-gpu.yaml`) and make sure all the required package to make your GPU accessible through docker are available too (drivers, container-toolkit).


#### Nvidia setup

The examples are shown from an Ubuntu OS.

- Choose the driver related to your CPU through their website or cli tools from your distribution if there is none installed
```sh
sudo apt install -y ubuntu-drivers-common
ubuntu-drivers devices # This will output the available drivers like for example: nvidia-driver-535
sudo apt install nvidia-driver-535 # the driver you need, you will need to reboot 
```

- Add the NVIDIA package repositories and install the nvidia container tool-kit
```sh
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
```

- Configure docker to use nvidia runtime, then reboot docker-engine
```sh
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```