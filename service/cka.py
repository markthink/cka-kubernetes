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

import sys,logging,yaml,click
from tools.cka_tools import CKATools
from pyfiglet import Figlet

click.disable_unicode_literals_warning = True
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S',
                    filename='./logs/cka.log',
                    filemode='w')
# 获取日志记录器
logger = logging.getLogger('cka')

def check_setting_and_env():
    logger.info("程序正在启动,检查环境配置")
    if sys.version_info < (3, 2):
        raise RuntimeError("at least Python 3.6 is required!!")
    logger.info("开始配置环境")

# http://click.pocoo.org/6/api/
@click.command()
@click.help_option('-h', '--help', help='CKA KUBERNETES - 运行参考')
@click.option('-s', '--ssl', type=click.Choice(['init', 'clear']), help='Task1 生成 SSL 证书')
@click.option('-k', '--kubeconfig', type=click.BOOL, default=False, help='Task2 生成 Kubeconfig 命令')
@click.option('-e', '--etcd', type=click.BOOL, default=False, help='Task3 生成 etcd 服务配置')
@click.option('-m', '--master', type=click.BOOL, default=False, help='Task4 生成 maser 服务配置')
@click.option('-n', '--node', type=click.BOOL, default=False, help='Task5 生成 node 服务配置')
@click.option('-d', '--dns', type=click.BOOL, default=False, help='Task6 生成 coredns 配置')
@click.option('-c', '--copy', type=click.BOOL, default=False, help='Task7 二进制文件复制')
@click.option('-b', '--bin', type=click.BOOL, default=False, help='Task8 二进制文件分发')
@click.option('-v', '--verify', type=click.BOOL, default=False, help='Task9 下发服务')
@click.option('-r', '--ret', type=click.Choice(['flannel', 'master', 'node']),help='Task10 启动服务')
@click.option('-down', '--down', type=click.BOOL, default=False,  help='Task11 清理环境')
@click.version_option(version='cka v1.0',message='%(version)s', help='显示程序版本号')
def parse_command(ssl, kubeconfig, etcd, master, node, dns, copy, bin, verify, ret, down):
    logger.info("正在检查环境")
    check_setting_and_env()

    logger.info("环境检查完毕,启动管理任务")

    # 加载配置文件
    with open('config.yaml', 'r') as file:
        config = yaml.load(file.read())

    cka = CKATools(config)

    if ssl == 'clear':
        cka.InitSSL(ssl)
        click.secho('Step1.清理证书~', fg='yellow', bg='black')
    elif ssl == 'init':
        cka.InitSSL(ssl)
        click.secho('Step1.配置证书~', fg='yellow', bg='black')

    if kubeconfig == True:
        cka.InitConfig()
        click.secho('Step2.kubeconfig 配置完毕~', fg='yellow', bg='black')

    if etcd == True:
        cka.InitETCD()
        click.secho('Step3.ECTD 配置完毕~', fg='yellow', bg='black')

    if master == True:
        cka.InitMaster()
        click.secho('Step4.Master 配置完毕~', fg='yellow', bg='black')

    if node == True:
        cka.InitNode()
        click.secho('Step5.Node 配置完毕~', fg='yellow', bg='black')

    if dns == True:
        cka.InitCoreDNS()
        click.secho('Step6. CoreDNS 配置完毕~', fg='yellow', bg='black')

    if copy == True:
        cka.BinCopy()
        click.secho('Step7. 文件提取完毕~', fg='yellow', bg='black')

    if bin == True:
        cka.BinDeploy()
        click.secho('Step8. 文件部署完毕~', fg='yellow', bg='black')

    if verify == True:
        cka.VerifyService()
        click.secho('Step9. 服务下发~', fg='yellow', bg='black')

    if ret == 'flannel':
        cka.RetDeploy(ret)
        click.secho('Step10. 启动 flanneld 服务~', fg='yellow', bg='black')
    elif ret == 'master':
        cka.RetDeploy(ret)
        click.secho('Step10. 启动 master 服务~', fg='yellow', bg='black')
    elif ret == 'node':
        cka.RetDeploy(ret)
        click.secho('Step10. 启动 node 服务~', fg='yellow', bg='black')

    if down == True:
        cka.DownKube()
        click.secho('Step11. 服务清理', fg='yellow', bg='black')
        
if __name__ == '__main__':
    # Ascii Art
    k8sArt = Figlet(font='slant')
    print(k8sArt.renderText('CKAK8S'))
    print('by xiaolong@caicloud.io  2018-4-7')

    # 默认打印帮助信息
    if len(sys.argv) == 1:
        sys.argv.append('-h')

    parse_command()