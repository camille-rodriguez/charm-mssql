# Deployment Preparation

This charm deploys on top of Kubernetes. It uses a submodule called the 
operator framework. If you are deploying from the charm store, this step is not
necessary. If you are cloning from source, you need to update the
submodule:
```
git clone https://github.com/canonical/charm-mssql.git
git submodule init
git submodule update
```

# MicroK8s Setup

```
sudo snap install juju --classic
sudo snap install microk8s --classic
microk8s.enable dns dashboard registry storage
juju bootstrap microk8s
juju create-storage-pool operator-storage kubernetes storage-class=microk8s-hostpath
juju deploy ./mssql
```

# MSSQL config options
`MSSQL_PID value`: "Developer": Sets the container to run SQL Server Developer 
edition. Developer edition is not licensed for production data. If the 
deployment is for production use, set the appropriate edition (Enterprise, 
Standard, or Express).
For more information, see How to license SQL Server: 
https://www.microsoft.com/sql-server/sql-server-2017-pricing.

`persistentVolumeClaim`: This value requires an entry for claimName: that maps 
to the name used for the persistent volume claim. This tutorial uses mssql-data.

`sa_password`: When Kubernetes deploys the container, the database 
is initialized with the username 'SA' and the password comes from the 
secret named `mssql`. The password can be changed in the config.yaml file. 

By using the `LoadBalancer` service type, the SQL Server instance is accessible 
remotely (via the internet) at port 1433.

If you are deploying locally on top of MicroK8s, the service is reachable over
the port-forwarding configuration. For example, for a service exposed like this:
```
NAMESPACE NAME           TYPE          CLUSTER-IP     EXTERNAL-IP  PORT(S)
mssql     service/mssql  LoadBalancer  10.152.183.16  <pending>    1443:32542/TCP
```
And a host of IP `192.168.1.75`, then the service would be reachable at
`192.168.1.75:32542`. 

# SQL Command-Line tools
To communicate with the database, the sql utility comes handy. It is included
by default in the mssql container, at /opt/mssql-tools/bin/sqlcmd. You can then
execute inside the container to use it. For example:
``` 
ubuntu@ubuntu:~$: microk8s.kubectl exec pod/mssql-0 -n mssql -it -- /bin/bash
root@mssql-0:/# /opt/mssql-tools/bin/sqlcmd -U SA -P "MyC0m9l&xP@ssw0rd"
```
If you want to install the sql command-line tools on a different host, 
instructions are here : https://docs.microsoft.com/en-us/sql/linux/sql-server-linux-setup-tools?view=sql-server-ver15#ubuntu .
To connect to the database, you will need to specify the server address and 
port, i.e: 

```
ubuntu@ubuntu:~$: sqlcmd -S 192.168.1.75,32038  -U sa -P "MyC0m9l&xP@ssw0rd"
1> select name from sys.databases
2> go
name                                                                                                                            
--------------------------------------------------------------------------------------------------------------------------------
master                                                                                                                          
tempdb                                                                                                                          
model                                                                                                                           
msdb  
(4 rows affected)
1>
```
