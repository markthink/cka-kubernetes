etcdctl --endpoints=${ETCD_ENDPOINTS} \
--ca-file=/etc/kubernetes/ssl/ca.pem \
--cert-file=/etc/kubernetes/ssl/kubernetes.pem \
--key-file=/etc/kubernetes/ssl/kubernetes-key.pem \
set ${FLANNEL_ETCD_PREFIX}/config '{"Network": "${CLUSTER_CIDR}", "SubnetLen": 24, "Backend": {"Type": "vxlan"}}'