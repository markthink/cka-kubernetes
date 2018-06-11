# -*- coding: utf-8 -*-

# Copyright 2018 The xiaolong@caicloud.io Authors.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# | 网络名称 |    网络范围     |
# |:--------:|:---------------:|
# | 集群网络 |  172.30.0.0/16  |
# | 服务网络 |  10.254.0.0/16  |
# | 物理网络 | 192.168.20.0/24 |

# vagrant ssh master
# ~ sudo su
# # passwd root

# sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config && 
# sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/g' /etc/ssh/sshd_config && 
# systemctl restart sshd
# ln -s /usr/bin/python3 /usr/bin/python
# ansible-playbook -i inventory cluster.yaml

import os,shutil,subprocess,re,logging,json

# 获取日志记录器
logger = logging.getLogger('cka')

class CKATools:
    # 初始化-获取所有环境配置
    def __init__(self, config):
        # 配置服务模板
        self.BASE_DIR = 'files/template/'

        self.ETCD_ONE = 'etcd/etcd-one.service'
        self.ETCD_MORE = 'etcd/etcd.service'
        self.ETCD_NETWORK = 'etcd/etcd_flannel.sh'

        self.MASTER_APISERVER = 'master/kube-apiserver.service'
        self.MASTER_CONTROLLER = 'master/kube-controller-manager.service'
        self.MASTER_SCHEDULER = 'master/kube-scheduler.service'
        self.NODE_FLANNELD = 'node/flanneld.service'
        self.NODE_PROXY = 'node/kube-proxy.service'
        self.NODE_KUBELET = 'node/kubelet.service'

        self.CONFIG_KUBELET = 'config/kubelet.kubeconfig'
        self.CONFIG_KUBEPROXY = 'config/kube-proxy.kubeconfig'
        self.CONFIG_KUBECTL = 'config/kubectl.kubeconfig'


        self.BOOTSTRAP_TOKEN = config['cka']['BOOTSTRAP_TOKEN']
        self.SERVICE_CIDR = config['cka']['SERVICE_CIDR']
        self.CLUSTER_CIDR = config['cka']['CLUSTER_CIDR']

        self.CLUSTER_KUBERNETES_SVC_IP = config['cka']['CLUSTER_KUBERNETES_SVC_IP']
        self.CLUSTER_DNS_SVC_IP = config['cka']['CLUSTER_DNS_SVC_IP']
        self.CLUSTER_DNS_DOMAIN = config['cka']['CLUSTER_DNS_DOMAIN']

        self.FLANNEL_ETCD_PREFIX = config['cka']['FLANNEL_ETCD_PREFIX']
        self.ETCD_ENDPOINTS = config['cka']['ETCD_ENDPOINTS']
        self.NODE_PORT_RANGE = config['cka']['NODE_PORT_RANGE']
        self.MASTER_IP = config['cka']['MASTER_IP']
        self.NODE_IP = config['cka']['NODE_IP']
        self.PAUSE_IMAGE = config['cka']['PAUSE_IMAGE']

    # 生成 ca 证书文件
    def InitSSL(self, action='clear'):
        SSL_DIR = 'gen/ssl/'
        if not os.path.exists(SSL_DIR):
            shutil.copytree('files/ssl/', SSL_DIR)

        if action == 'clear':
            rm_cmd = "cd " + SSL_DIR +" && ls | grep -v json | xargs rm -rf"
            subprocess.run(rm_cmd, shell=True)
            logger.info('Step1. 证书清理完毕..')
        elif action == 'init':
            # 生成 token 文件
            with open(SSL_DIR+'/token.csv', 'w') as file:
                file.write(self.BOOTSTRAP_TOKEN+',kubelet-bootstrap,10001,"system:kubelet-bootstrap"')

            with open(SSL_DIR + "kubernetes-csr.json", encoding='utf8') as file:
                content = file.read()
                csr = json.loads(content)
                ips = re.findall(r'\d+.\d+.\d+.\d+', self.ETCD_ENDPOINTS)
                if len(ips)==1:
                    if ips[0] == self.MASTER_IP:
                        csr['hosts'].insert(1, self.MASTER_IP)
                        csr['hosts'].insert(2, self.CLUSTER_KUBERNETES_SVC_IP)
                else:
                    # 设置步进，用于指定插入位置
                    setp = 0
                    for ip in ips:
                        setp += 1
                        if ip == self.MASTER_IP:
                            csr['hosts'].insert(1, self.MASTER_IP)
                        else:
                            csr['hosts'].insert(setp, ip)
                    csr['hosts'].insert(setp+1, self.CLUSTER_KUBERNETES_SVC_IP)

                # print(csr['hosts'])
            with open(SSL_DIR + "kubernetes-csr.json", 'w') as file:
                json.dump(csr, file, sort_keys=True, indent=4, ensure_ascii=False)

            init_ssl = '''
cd gen/ssl && echo -e 'admin,admin,1\nsystem,system,2' >> basic_auth_file
cfssl gencert -initca csr.json | cfssljson -bare ca
for target in kubernetes admin kube-proxy flanneld; do
    cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=config.json -profile=kubernetes $target-csr.json | cfssljson -bare $target
done
'''
            subprocess.run(init_ssl, shell=True)
            logger.info('Step1. 证书生成完毕..')

    # 生成 kubeconfig
    def InitConfig(self):
        CONFIG_DIR = 'gen/config/'
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)

        # 生成 kubelet 配置命令 - Create kubelet bootstrapping kubeconfig...
        with open(self.BASE_DIR + self.CONFIG_KUBELET, encoding='utf8') as file:
            kubelet_content = file.read()
            kubelet_content = re.sub('\$\{KUBE_APISERVER\}', 'https://'+self.MASTER_IP+':6443', kubelet_content)
            kubelet_content = re.sub('\$\{BOOTSTRAP_TOKEN\}', self.BOOTSTRAP_TOKEN, kubelet_content)

        # 生成 kube-proxy 配置命令 - Create kube-proxy kubeconfig...
        with open(self.BASE_DIR + self.CONFIG_KUBEPROXY, encoding='utf8') as file:
            kubeproxy_content = file.read()
            kubeproxy_content = re.sub('\$\{KUBE_APISERVER\}', 'https://' + self.MASTER_IP + ':6443', kubeproxy_content)

        # 生成 kubectl 配置命令 - 集群管理员 admin kubeconfig 配置-供 kubectl 调用使用
        with open(self.BASE_DIR + self.CONFIG_KUBECTL, encoding='utf8') as file:
            kubectl_content = file.read()
            kubectl_content = re.sub('\$\{KUBE_APISERVER\}', 'https://' + self.MASTER_IP + ':6443', kubectl_content)

        with open(CONFIG_DIR + 'kubeconfig', 'w') as file:
            file.write(kubelet_content+'\n\n'+kubeproxy_content+'\n\n'+kubectl_content)

        # 生成配置 xx.kubeconfig
        with open(CONFIG_DIR +'kubeconfig', encoding='utf8') as file:
            content = file.read()
            subprocess.run('cd gen/ssl &&'+content, shell=True)

        logger.info('Step2. kubeconfig 配置命令生成完毕..')
    
    # one 单 etcd ,more etcd cluster
    def etcd_tools(self):
        etcd_status = []
        ips = re.findall(r'\d+.\d+.\d+.\d+', self.ETCD_ENDPOINTS)
        if len(ips) == 1:
            etcd_list = self.ETCD_ENDPOINTS

            etcd_status.append('one')
            etcd_status.append(etcd_list)
        else:
            temp=[]
            endponts = self.ETCD_ENDPOINTS.split(',')
            for end in endponts:
                endpoint = end.split('=')
                temp.append(endpoint[1]) 
            etcd_list = ",".join(temp)
            
            etcd_status.append('more')
            etcd_status.append(etcd_list)
        return etcd_status

    # 生成 etcd 配置文件
    def InitETCD(self):
        ETCD_DIR='gen/etcd/'
        # 自动生成路径
        if not os.path.exists(ETCD_DIR):
            os.makedirs(ETCD_DIR)

        eds = self.etcd_tools()
        if eds[0] == 'one': # 生成单节点的 ETCD
            with open(self.BASE_DIR+self.ETCD_ONE, encoding='utf8') as file:
                content = file.read()
                content = re.sub('\$\{ETCD_IP\}', self.MASTER_IP, content)

            with open(ETCD_DIR+'etcd.service', 'w', encoding='utf8') as file:
                file.write(content)
            logger.info('init one etcd')
        elif eds[0] == 'more': # 生成集群 ETCD
            etcds = self.ETCD_ENDPOINTS.split(',')
            for node in etcds:
                etcd = node.split('=')
                etcd_name = etcd[0]
                etcd_ip = re.findall(r'\d+.\d+.\d+.\d+',etcd[1])[0]
                with open(self.BASE_DIR+self.ETCD_MORE, encoding='utf8') as file:
                    content = file.read()
                    content = re.sub('\$\{ETCD_NAME\}', etcd_name, content)
                    content = re.sub('\$\{ETCD_IP\}', etcd_ip, content)
                    content = re.sub('\$\{ETCD_NODES\}', re.sub('2379', '2380',self.ETCD_ENDPOINTS), content)
                with open(ETCD_DIR+etcd_name+'.service', 'w', encoding='utf8') as file:
                    file.write(content)

        # ETCD Flanneld 网段生成
        with open(self.BASE_DIR+self.ETCD_NETWORK, encoding='utf8') as file:
            flannel = file.read()
            flannel = re.sub('\$\{ETCD_ENDPOINTS\}', eds[1], flannel)
            flannel = re.sub('\$\{FLANNEL_ETCD_PREFIX\}', self.FLANNEL_ETCD_PREFIX, flannel)
            flannel = re.sub('\$\{CLUSTER_CIDR\}', self.CLUSTER_CIDR, flannel)

        with open(ETCD_DIR+'etcd_flannel.sh', 'w', encoding='utf8') as file:
            file.write(flannel)

            logger.info('init more etcd')

    def InitMaster(self):
        MASTER_DIR = 'gen/master/'
        # 自动生成路径
        if not os.path.exists(MASTER_DIR):
            os.makedirs(MASTER_DIR)

        eds = self.etcd_tools()

        # 生成 Master 配置文件
        # 生成 apiserver 服务配置
        with open(self.BASE_DIR+self.MASTER_APISERVER, encoding='utf8') as file:
            content = file.read()
            content = re.sub('\$\{MASTER_IP\}', self.MASTER_IP, content)
            content = re.sub('\$\{SERVICE_CIDR\}', self.SERVICE_CIDR, content)
            content = re.sub('\$\{NODE_PORT_RANGE\}', self.NODE_PORT_RANGE, content)
            content = re.sub('\$\{ETCD_ENDPOINTS\}', eds[1], content)

        with open(MASTER_DIR+'kube-apiserver.service', 'w') as file:
            file.write(content)

        # 生成 controller-manager 配置
        with open(self.BASE_DIR+self.MASTER_CONTROLLER, encoding='utf8') as file:
            content = file.read()
            content = re.sub('\$\{MASTER_IP\}', self.MASTER_IP, content)
            content = re.sub('\$\{SERVICE_CIDR\}', self.SERVICE_CIDR, content)
            content = re.sub('\$\{CLUSTER_CIDR\}', self.CLUSTER_CIDR, content)

        with open(MASTER_DIR+'kube-controller-manager.service', 'w') as file:
            file.write(content)

        # 生成 scheduler 配置
        with open(self.BASE_DIR+self.MASTER_SCHEDULER, encoding='utf8') as file:
            content = file.read()
            content = re.sub('\$\{MASTER_IP\}', self.MASTER_IP, content)

        with open(MASTER_DIR+'kube-scheduler.service', 'w') as file:
            file.write(content)

        logger.info('init master')

    def InitNode(self):
        nodes = self.NODE_IP.split(',')
        for i in range(0, len(nodes)):
            NODE_DIR = 'gen/node'+str(i)+'/'
            node_ip = nodes[i]
            if i == 0:
                node_name = 'kube-master'
            else:
                node_name = 'kube-node'+str(i)
            # 自动生成路径
            if not os.path.exists(NODE_DIR):
                os.makedirs(NODE_DIR)

            # 生成 Node 配置文件
            # 生成 kubelet 服务配置
            with open(self.BASE_DIR + self.NODE_KUBELET, encoding='utf8') as file:
                content = file.read()
                content = re.sub('\$\{NODE_NAME\}', node_name, content)
                content = re.sub('\$\{NODE_IP\}', node_ip, content)
                content = re.sub('\$\{PAUSE_IMAGE\}', self.PAUSE_IMAGE, content)
                content = re.sub('\$\{CLUSTER_DNS_SVC_IP\}', self.CLUSTER_DNS_SVC_IP, content)
                content = re.sub('\$\{CLUSTER_DNS_DOMAIN\}', self.CLUSTER_DNS_DOMAIN, content)

            with open(NODE_DIR + 'kubelet.service', 'w') as file:
                file.write(content)

            # 生成 kube-proxy 配置
            with open(self.BASE_DIR + self.NODE_PROXY, encoding='utf8') as file:
                content = file.read()
                content = re.sub('\$\{NODE_NAME\}', node_name, content)
                content = re.sub('\$\{NODE_IP\}', node_ip, content)
                content = re.sub('\$\{CLUSTER_CIDR\}', self.CLUSTER_CIDR, content)

            with open(NODE_DIR + 'kube-proxy.service', 'w') as file:
                file.write(content)

            # 生成 flanneld 配置
            eds = self.etcd_tools()
            with open(self.BASE_DIR + self.NODE_FLANNELD, encoding='utf8') as file:
                content = file.read()
                content = re.sub('\$\{NODE_IP\}', node_ip, content)
                content = re.sub('\$\{ETCD_ENDPOINTS\}', eds[1], content)
                content = re.sub('\$\{FLANNEL_ETCD_PREFIX\}', self.FLANNEL_ETCD_PREFIX, content)

            with open(NODE_DIR + 'flanneld.service', 'w') as file:
                file.write(content)
        logger.info('init node')

    def InitCoreDNS(self):
        YAML_DIR = 'gen/yaml/'
        if not os.path.exists(YAML_DIR):
            shutil.copytree('files/yaml/', YAML_DIR)

        with open(YAML_DIR + "coredns.yaml", encoding='utf8') as file:
            content = file.read()
            content = re.sub('\$\{CLUSTER_DNS_DOMAIN\}', self.CLUSTER_DNS_DOMAIN, content)
            content = re.sub('\$\{SERVICE_CIDR\}', self.SERVICE_CIDR, content)
            content = re.sub('\$\{CLUSTER_DNS_SVC_IP\}', self.CLUSTER_DNS_SVC_IP, content)

        with open(YAML_DIR+'coredns.yaml', 'w') as file:
            file.write(content)
        logger.info('init coredns')

    # 分发二进制文件与配置文件
    def BinCopy(self):
        # mkdir -p down/flannel && cd down\
        # wget https://dl.k8s.io/v1.10.0/kubernetes-server-linux-amd64.tar.gz
        # wget https://github.com/coreos/etcd/releases/download/v3.2.18/etcd-v3.2.18-linux-amd64.tar.gz
        # wget https://github.com/coreos/flannel/releases/download/v0.10.0/flannel-v0.10.0-linux-amd64.tar.gz
        # tar -xf flannel-v0.10.0-linux-amd64.tar.gz -C flannel \
        # tar -xf etcd-v3.2.18-linux-amd64.tar.gz \
        # tar -xf kubernetes-server-linux-amd64-v1.10.0.tar.gz \
        # 生成指定的目录
        for path in ['etcd','master','node']:
            file_path = 'deploy/'+path
            if not os.path.exists(file_path):
                os.makedirs(file_path)

        shutil.copy('../down/kubernetes/server/bin/kubelet','deploy/node/')
        shutil.copy('../down/kubernetes/server/bin/kube-proxy','deploy/node/')
        shutil.copy('../down/flannel/mk-docker-opts.sh','deploy/node/')
        shutil.copy('../down/flannel/flanneld','deploy/node/')
        shutil.copy('../down/kubernetes/server/bin/kube-apiserver','deploy/master/')
        shutil.copy('../down/kubernetes/server/bin/kube-controller-manager','deploy/master/')
        shutil.copy('../down/kubernetes/server/bin/kube-scheduler','deploy/master/')
        shutil.copy('../down/kubernetes/server/bin/kubectl','deploy/master/')
        shutil.copy('../down/etcd-v3.2.18-linux-amd64/etcd','deploy/etcd/')
        shutil.copy('../down/etcd-v3.2.18-linux-amd64/etcdctl','deploy/etcd/')

        logger.info('Bin Copy')

    # 下发二进制文件
    def BinDeploy(self):
        deploy = '''
for etcd in master node1 node2 ;do
    rsync -avzP deploy/etcd/ ${etcd}:/usr/local/bin/
done
for master in master ;do
    rsync -avzP deploy/master/ ${master}:/usr/local/bin/
done
for node in master node1 node2 ;do
    rsync -avzP deploy/node/ ${node}:/usr/local/bin/
done
'''
        subprocess.run(deploy, shell=True)
        logger.info('Bin Copy')

    def VerifyService(self):
        eds = self.etcd_tools()
        if eds[0] == 'one':
            etcd = '''
rsync -avzP gen/etcd/etcd.service master:/etc/systemd/system/etcd.service
'''
        elif eds[0] == 'more':
            etcd = '''
rsync -avzP gen/etcd/infra1.service master:/etc/systemd/system/etcd.service
rsync -avzP gen/etcd/infra2.service node1:/etc/systemd/system/etcd.service
rsync -avzP gen/etcd/infra3.service node2:/etc/systemd/system/etcd.service
'''
        service = '''
for node in master node1 node2 ;do
    ssh ${node} "mkdir -p /etc/kubernetes/ssl/ "
    ssh ${node} "mkdir -p /var/lib/etcd/"
    ssh ${node} "mkdir -p /var/lib/kubelet/"
    ssh ${node} "mkdir -p /var/lib/kube-proxy/"
done

for node in master node1 node2 ;do
    rsync -avzP gen/ssl/  ${node}:/etc/kubernetes/ssl/
done

for master in master ;do
    ssh ${master} "mkdir -p /root/.kube ; \cp -f /etc/kubernetes/ssl/kubeconfig  /root/.kube/config "
done

rsync -avzP gen/node0/ master:/etc/systemd/system/
rsync -avzP gen/node1/ node1:/etc/systemd/system/
rsync -avzP gen/node2/ node2:/etc/systemd/system/

for master in master ;do
    rsync -avzP gen/master/ ${master}:/etc/systemd/system/
done
'''
        subprocess.run(etcd + service, shell=True)
        # 写入 etcd 网段信息-需要手动在 Master 节点执行
        with open('gen/etcd/etcd_flannel.sh', encoding='utf8') as file:
            network = file.read()
        # 检测 etcd 状态
        etcd_check = '''
systemctl daemon-reload && systemctl start etcd && systemctl enable etcd

Master Run: 
ETCDCTL_API=3 etcdctl --endpoints=${ETCD_ENDPOINTS} --cacert=/etc/kubernetes/ssl/ca.pem --cert=/etc/kubernetes/ssl/kubernetes.pem --key=/etc/kubernetes/ssl/kubernetes-key.pem endpoint health;
etcdctl --endpoints=${ETCD_ENDPOINTS} --ca-file=/etc/kubernetes/ssl/ca.pem  --cert-file=/etc/kubernetes/ssl/kubernetes.pem --key-file=/etc/kubernetes/ssl/kubernetes-key.pem get /kubernetes/network/config
        '''
        print(re.sub('\$\{ETCD_ENDPOINTS\}', eds[1], etcd_check) + "\n" + network)

    def RetDeploy(self, action='flannel'):

        if action == 'flannel':
            content = '''
for node in master node1 node2 ;do
    ssh ${node} "systemctl daemon-reload && systemctl stop docker && systemctl start flanneld docker && systemctl enable flanneld"
done
            '''
        elif action == 'master':
            content = '''
for master in master ;do
    ssh ${master} "systemctl daemon-reload && systemctl start kube-apiserver kube-controller-manager kube-scheduler && systemctl enable kube-apiserver kube-controller-manager kube-scheduler"
done
            '''
            # kubelet 依赖于 bootstrap 角色绑定
            bootstrap = '''
echo -e "192.168.20.151 kube-master\n192.168.20.152 kube-node1\n192.168.20.153 kube-node2" >> /etc/hosts
kubectl create clusterrolebinding kubelet-bootstrap --clusterrole=system:node-bootstrapper  --user=kubelet-bootstrap 
'''
            print(bootstrap)
        elif action == 'node':
            content = '''
for node in master node1 node2 ;do
    ssh ${node} "systemctl daemon-reload && systemctl start kubelet kube-proxy && systemctl enable kubelet kube-proxy"
done
            '''
            # 验证集群
            verify_cluster = '''
kubectl get csr | awk '/Pending/ {print $1}' | xargs kubectl certificate approve
'''
            print(verify_cluster)

        subprocess.run(content, shell=True)
        logger.info('complete cluster')

    # 环境清理脚本
    def DownKube(self):
        ips = re.findall(r'\d+.\d+.\d+.\d+', self.ETCD_ENDPOINTS)
        if len(ips) == 1:
            etcd = '''
ssh master "rm -rf /etc/systemd/system/etcd.service"
'''
        else:
            etcd = '''
for etcd in master node1 node2; do
    ssh ${etcd} "rm -rf /etc/systemd/system/etcd.service"
done
'''
        init = '''
for node in master node1 node2; do
    ssh ${node} "systemctl daemon-reload && systemctl stop kublet kube-proxy"
done

for master in master; do
    ssh ${master} "systemctl stop kube-scheduler kube-controller-manager kube-apiserver flanneld docker"
done

for etcd in master; do
    ssh ${etcd} "systemctl stop etcd"
done

for node in master node1 node2 ;do
    ssh ${node} "rm -rf /etc/kubernetes/ssl/ /etc/systemd/system/flanneld.service  /etc/systemd/system/flanneld.service /etc/systemd/system/kube-proxy.service /etc/systemd/system/kubelet.service"
done
for master in master ;do
    ssh ${master} "rm -rf /etc/systemd/system/kube-apiserver.service /etc/systemd/system/kube-controller-manager.service  /etc/systemd/system/kube-scheduler.service"
done
'''

        dirname = '''
for node in master node1 node2 ;do
    ssh ${node} "systemctl daemon-reload && rm -rf /etc/kubernetes/ssl/ /var/lib/etcd/ /var/lib/kubelet/ /var/lib/kube-proxy/" 
done
'''
        # 清理 ssl 证书与服务文件
        # print(init+etcd+dirname)
        subprocess.run(init+etcd+dirname, shell=True)
        logger.info('clear cluster')
