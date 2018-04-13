# CKA Kubernetes 配置

## 安装 Go 语言环境:

```
tar -C /usr/local -xzf go1.10.1.linux-amd64.tar.gz
mkdir /go
cat /etc/profile
export PATH=$PATH:/usr/local/go/bin:/go/bin
export GOROOT=/usr/local/go
export GOPATH=/go
```
source /etc/profile

源码安装 ssl 工具：

```
go get -u github.com/cloudflare/cfssl/cmd/...
ls /go/bin/cfssl*
```

kubernetes 各组件证书文件概要-(etcd 证书可不用单独生成，共用 kubernetes 证书)

| CA & Key           | etcd | kube-apiserver | kube-proxy | kubelet | kubectl | flanneld |
|:-------------------|:----:|:--------------:|:----------:|:-------:|:-------:|:--------:|
| ca.pem             | must |      must      |    must    |  must   |  must   |   must   |
| ca-key.pem         |  -   |       -        |     -      |    -    |    -    |    -     |
| kubernetes.pem     |  -   |      must      |     -      |    -    |    -    |    -     |
| kubernetes-key.pem |  -   |      must      |     -      |    -    |    -    |    -     |
| kube-proxy.pem     |  -   |       -        |    must    |    -    |    -    |    -     |
| kube-proxy-key.pem |  -   |       -        |    must    |    -    |    -    |    -     |
| admin.pem          |  -   |       -        |     -      |    -    |  must   |    -     |
| admin-key.pem      |  -   |       -        |     -      |    -    |  must   |    -     |
| flanneld.pem       |  -   |       -        |     -      |    -    |    -    |   must   |
| flanneld-key.pem   |  -   |       -        |     -      |    -    |    -    |   must   |


## 生成证书文件

```
cfssl gencert -initca csr.json | cfssljson -bare ca
for target in kubernetes admin kube-proxy flanneld; do
    cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=config.json -profile=kubernetes $target-csr.json | cfssljson -bare $target
done
```

校验证书

以校验 kubernetes 证书：

使用 `openssl` 命令

``` bash
$ openssl x509  -noout -text -in  kubernetes.pem
```
+ 确认 `Issuer` 字段的内容和 `csr.json` 一致；
+ 确认 `Subject` 字段的内容和 `kubernetes-csr.json` 一致；
+ 确认 `X509v3 Subject Alternative Name` 字段的内容和 `kubernetes-csr.json` 一致；
+ 确认 `X509v3 Key Usage、Extended Key Usage` 字段的内容和 `ca-config.json` 中 `kubernetes` profile 一致；

cfssl-certinfo:

```
cfssl-certinfo -cert kubernetes.pem

export KUBE_APISERVER="https://${MASTER_IP}:6443"
export BOOTSTRAP_TOKEN=$(head -c 16 /dev/urandom | od -An -t x | tr -d ' ')
echo "Tokne: ${BOOTSTRAP_TOKEN}"

cat > token.csv <<EOF
${BOOTSTRAP_TOKEN},kubelet-bootstrap,10001,"system:kubelet-bootstrap"
EOF
```

配置集群参数：

Create kubelet bootstrapping kubeconfig...

```bash
kubectl config set-cluster kubernetes \
--certificate-authority=ca.pem \
--embed-certs=true \
--server=${KUBE_APISERVER} \
--kubeconfig=bootstrap.kubeconfig

kubectl config set-credentials kubelet-bootstrap \
--token=${BOOTSTRAP_TOKEN} \
--kubeconfig=bootstrap.kubeconfig

kubectl config set-context default \
 --cluster=kubernetes \
 --user=kubelet-bootstrap \
 --kubeconfig=bootstrap.kubeconfig

kubectl config use-context default --kubeconfig=bootstrap.kubeconfig
```

Create kube-proxy kubeconfig...

```
kubectl config set-cluster kubernetes \
--certificate-authority=ca.pem \
--embed-certs=true \
--server=${KUBE_APISERVER} \
--kubeconfig=kube-proxy.kubeconfig

kubectl config set-credentials kube-proxy \
--client-certificate=kube-proxy.pem \
--client-key=kube-proxy-key.pem \
--embed-certs=true \
--kubeconfig=kube-proxy.kubeconfig

kubectl config set-context default \
 --cluster=kubernetes \
 --user=kube-proxy \
 --kubeconfig=kube-proxy.kubeconfig

kubectl config use-context default --kubeconfig=kube-proxy.kubeconfig
```

集群管理员 admin kubeconfig 配置-供 kubectl 调用使用

```
kubectl config set-cluster kubernetes \
--certificate-authority=ca.pem \
--embed-certs=true \
--server=${KUBE_APISERVER} \
--kubeconfig=./kubeconfig

kubectl config set-credentials kubernetes-admin \
--client-certificate=admin.pem \
--client-key=admin-key.pem \
--embed-certs=true \
--kubeconfig=./kubeconfig

kubectl config set-context xiaolong@caicloud.io \
 --cluster=kubernetes \
 --user=kubernetes-admin \
 --kubeconfig=./kubeconfig

kubectl config use-context xiaolong@caicloud.io --kubeconfig=./kubeconfig
```


## 向 etcd 写入集群 Pod 网段信息

注意：本步骤只需在**第一次**部署 Flannel 网络时执行，后续在其它节点上部署 Flannel 时**无需**再写入该信息！

``` bash
etcdctl --endpoints=${ETCD_ENDPOINTS} \
  --ca-file=/etc/kubernetes/ssl/ca.pem \
  --cert-file=/etc/kubernetes/ssl/kubernetes.pem \
  --key-file=/etc/kubernetes/ssl/kubernetes-key.pem \
  set ${FLANNEL_ETCD_PREFIX}/config \
  '{"Network":"'${CLUSTER_CIDR}'", "SubnetLen": 24, "Backend": {"Type": "vxlan"}}'

etcdctl --endpoints=${ETCD_ENDPOINTS} --ca-file=/etc/kubernetes/ssl/ca.pem  --cert-file=/etc/kubernetes/ssl/kubernetes.pem --key-file=/etc/kubernetes/ssl/kubernetes-key.pem ls /kubernetes/network/subnets
```

在 Master 机器上执行，授权 kubelet-bootstrap 角色

```
kubectl create clusterrolebinding kubelet-bootstrap \
  --clusterrole=system:node-bootstrapper \
  --user=kubelet-bootstrap
# 通过所有集群认证
kubectl get csr
kubectl get csr | awk '/Pending/ {print $1}' | xargs kubectl certificate approve
kubectl get no
```


