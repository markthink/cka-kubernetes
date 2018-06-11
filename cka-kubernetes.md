# 二进制安装 kubernetes

## 编译 cka 部署镜像

下载证书工具

```
mkdir cfssl && cd cfssl
wget https://pkg.cfssl.org/R1.2/cfssl_linux-amd64
chmod +x cfssl_linux-amd64
mv cfssl_linux-amd64 cfssl

wget https://pkg.cfssl.org/R1.2/cfssljson_linux-amd64
chmod +x cfssljson_linux-amd64
mv cfssljson_linux-amd64 cfssljson

wget https://pkg.cfssl.org/R1.2/cfssl-certinfo_linux-amd64
chmod +x cfssl-certinfo_linux-amd64
mv cfssl-certinfo_linux-amd64 cfssl-certinfo
```

下载 kubectl 工具

```
curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl
chmod +x ./kubectl

```

编译 cka:v1 镜像

```
cd ..
docker build -t cka:v1 -f Docker/Dockerfile .
```

## Step1. 下载二进制安装部署包并解压至 down 目录

```
mkdir -p down/flannel && cd down \ 
wget https://dl.k8s.io/v1.10.0/kubernetes-server-linux-amd64.tar.gz 
wget https://github.com/coreos/etcd/releases/download/v3.2.18/etcd-v3.2.18-linux-amd64.tar.gz
wget https://github.com/coreos/flannel/releases/download/v0.10.0/flannel-v0.10.0-linux-amd64.tar.gz
tar -xf flannel-v0.10.0-linux-amd64.tar.gz -C flannel \
tar -xf etcd-v3.2.18-linux-amd64.tar.gz \
tar -xf kubernetes-server-linux-amd64-v1.10.0.tar.gz \
```

下载二进制 docker 部署文件

```
cd ..
git clone https://github.com/markthink/cka-docker.git
```

查看目录结构

```
➜  down tree -L 2
.
├── etcd-v3.2.18-linux-amd64
│   ├── Documentation
│   ├── README-etcdctl.md
│   ├── README.md
│   ├── READMEv2-etcdctl.md
│   ├── etcd
│   └── etcdctl
├── etcd-v3.2.18-linux-amd64.tar.gz
├── flannel
│   ├── README.md
│   ├── flanneld
│   └── mk-docker-opts.sh
├── flannel-v0.10.0-linux-amd64.tar.gz
├── kubernetes
│   ├── LICENSES
│   ├── addons
│   ├── kubernetes-src.tar.gz
│   └── server
└── kubernetes-server-linux-amd64-v1.10.0.tar.gz
```

## Step2. 准备虚拟机环境


```Vagrantfile
# -*- mode: ruby -*-
# # vi: set ft=ruby :
# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

boxes = [
  {
    :name => "master",
    :eth1 => "192.168.20.151",
    :mem => "1024",
    :cpu => "2"
  },
  {
    :name => "node1",
    :eth1 => "192.168.20.152",
    :mem => "1024",
    :cpu => "2"
  },
  {
    :name => "node2",
    :eth1 => "192.168.20.153",
    :mem => "1024",
    :cpu => "2"
  }
]

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "ubuntu/xenial64"
  # Turn off shared folders
  config.vm.synced_folder ".", "/vagrant", id: "vagrant-root", disabled: true
  #config.vm.synced_folder "~/works/codelab/cka/files", "/files"
  # config.ssh.private_key_path = "~/.ssh/id_rsa"
  # config.ssh.forward_agent = true

  boxes.each do |opts|
    config.vm.define opts[:name] do |config|
      config.vm.hostname = opts[:name]
      config.ssh.insert_key = true
      # config.ssh.password = "vagrant"
      config.vm.provider "virtualbox" do |v|
        # v.gui = true
        v.customize ["modifyvm", :id, "--memory", opts[:mem]]
        v.customize ["modifyvm", :id, "--cpus", opts[:cpu]]
      end
      # config.vm.network :public_network
      config.vm.network "private_network", ip: opts[:eth1], auto_config: true
    end
  end
end

```

启动 vagrant 虚机

```
vagrant up
```

## Step3. 启动 cka:v1 部署容器

1. 祼 Docker 启动服务

```
docker run --add-host master:192.168.20.151 \
    --add-host node1:192.168.20.152 \
    --add-host node2:192.168.20.153 \
    -v `pwd`/down:/cka/down \
    -v `pwd`/cka-docker:/cka/docker \
    -ti cka:v1 sh
```

2. 使用 docker-compose 启动服务

cat docker-compose.yaml

```sh
version: '2'
services:
    cka: 
        image: cka:v1
        command: ["sh", "-c", "while true; do echo hello world; sleep 10; done"]
        volumes:
        - ./down:/cka/down
        - ./cka-docker:/cka/docker
        extra_hosts:
        - master:192.168.20.151
        - node1:192.168.20.152
        - node2:192.168.20.153    
```

Step3. 运行服务

解决虚拟机 root 用户密码方式登陆的问题

```
vagrant ssh master
~ sudo su
# passwd root

sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config && 
sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config && 
systemctl restart sshd
ln -s /usr/bin/python3 /usr/bin/python
```

安装 docker 

```
cd /cka/docker/tests
ansible-playbook -i inventory cluster.yaml
```

安装 kubernetes

```python
cd /cka/service 
python cka.py

# 生成证书
python cka.py -s init
# 生成 kubeconfig
python cka.py -k true
# 生成 etcd
python cka.py -e true
# 生成 master service
python cka.py -m true
# 生成 node service
python cka.py -n true
# 生成 yaml 服务配置-coredns
python cka.py -d true
# 拷贝二进制安装包
python cka.py -c true
# 下发二进制安装包
python cka.py -b true
# 下发服务+证书文件
python cka.py -v true

# 启动 master 服务
python cka.py -r flannel
# 启动 master 服务
python cka.py -r master
# 启动 node 服务
python cka.py -r node
```
