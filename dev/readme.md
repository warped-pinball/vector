How to setup:

linux:

raspbery pi:

install miniforge:
```bash
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh
chmod +x Miniforge3-Linux-aarch64.sh
./Miniforge3-Linux-aarch64.sh
```

create env and install requirements
```bash
conda create -n pico python=3.11
conda activate pico
pip install -r dev/requirements.txt
```

windows:

