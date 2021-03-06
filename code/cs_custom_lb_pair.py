#!/usr/bin/env python
# v 1.0
# Ryan Nguyen

# this script performs the following actions:
# 1. creates a specified number of 512MB cloud servers
# 2. prints out a compiled report of the created servers containing: id, public ipv4, private ipv4, root password
# 3. supplies a ssh key to each server, installed at /root/.ssh/authorized_keys.
# 4. creates a load balancer
# 5. Add the 2 new servers to the LB
# 6. Set up LB monitor 
# 7. creates and then sets a LB custom error page.
# 8. creates a DNS record based on a FQDN for the LB VIP
# 9. uploads the error page html to a file in cloud files for backup.

import os
import pyrax
import string
import re
import sys
import time
import common as helper

# prelimsies
seconds_before_retrying = 5
prefix = 'test'
creds_file = os.path.expanduser("~/.rackspace_cloud_credentials")
pyrax.set_credential_file(creds_file)
cs = pyrax.cloudservers
clb = pyrax.cloud_loadbalancers
cdns = pyrax.cloud_dns
cf = pyrax.cloudfiles

disp_time = helper.disp_time()

if len(sys.argv)<2:
        print '{0}: <number of servers>'.format(sys.argv[0])
        sys.exit(1)
else:
        num_servers = helper.strip_non_numbers(sys.argv[1])
        error = 'ERROR: you entered an invalid number of servers'
        if num_servers == '':
                print error
                sys.exit(1)
        num_servers = int(num_servers)
        if (num_servers < 1) or (num_servers > 50):
                print error, '[ either too few (0) or too many >50 ]'
                sys.exit(1)
        print 'building {0} servers...'.format(num_servers)

create_servers = []
for n in range (1, num_servers+1):
        create_servers.append(prefix+str(n))

# get all OS's in a list, filter list for Cent* matches, sort filtered list, and grab latest version
os_imgs = helper.act_loop(cs.images.list)

cent_os_imgs = [img for img in helper.act_loop(cs.images.list) if "Cent" in img.name]
cent_os_imgs.sort(key=lambda x: x.name, reverse=True)
latest_cent_os_img = cent_os_imgs[0]
# search flavsies, get 512* instance via match
sv_512 = [flavor for flavor in helper.act_loop(cs.flavors.list) if "512" in flavor.name][0]

# grab the SSH keys from the host so we can inject them into the server via files kwarg
with open ("/root/.ssh/authorized_keys", "r") as root_ssh_auth_keys:
	ssh_auth_file=root_ssh_auth_keys.read().replace('\n', '')
files = {"/root/.ssh/authorized_keys": ssh_auth_file}

# queue a list of servers to build out
queued_servers = []
data = {}
for host in create_servers:
        data = {
		'name': host, 
		'os_img_id': latest_cent_os_img.id, 
		'flavor_id': sv_512.id, 
		'files': files, 
		'completed': 'no'
		}
        queued_servers.append(data)

# build out the servers in the queue
finished_servers = helper.build_servers(queued_servers)
nodes = []
print ' '
print '-------------'
print 'YAY, TIME FOR THE BUILD REPORT..'
print '-------------'
print ' '
for svr in finished_servers:
        print "ID:", svr['id']
        print "Server:", svr['name']
        print "Public IP:", svr['pub']
        print "Private IP:", svr['priv']
        print "Admin password:", svr['pass']
        print '-------------'
        nodes.append(helper.act_loop(clb.Node, address=svr['priv'], port=80, condition="ENABLED"))

vip = helper.act_loop(clb.VirtualIP, type="PUBLIC")
default_algorithm = helper.act_loop(map, str, clb.algorithms)[0]
lb_name = '{0}-lb'.format(prefix)
lb = helper.act_loop(clb.create, lb_name, port="80", protocol="HTTP", nodes=nodes, virtual_ips=[vip], algorithm=default_algorithm)


while True:
        print 'checking server until LB is active...', disp_time 
        lb = helper.act_loop(clb.get, lb.id)
        if lb.status == 'ACTIVE':
                helper.act_loop(lb.add_health_monitor, type="CONNECT", delay=10, timeout=10, attemptsBeforeDeactivation=3)
                html_error_page = '<html><body><h1>stuff is messed up</h1><iframe width="420" height="315" src="http://www.youtube.com/embed/XYYo3T6nCw8?list=FLaE5b9q2s2yO77ZIXwqbHog&autoplay=1" frameborder="0" allowfullscreen></iframe></body></html>'
                while True:
                        print 'updating health montor..'
                        lb = helper.act_loop(clb.get, lb.id)
                        if lb.status == 'ACTIVE':
                                break
                helper.act_loop(lb.set_error_page, html_error_page)
                site_cont_name = '{0}-backup'.format(lb_name)
                cont = helper.act_loop(cf.get_container, site_cont_name)
                obj = helper.act_loop(cf.store_object, site_cont_name, "index.htm", html_error_page)
                for ip in lb.virtual_ips:
                        if helper.validate_ipv4(lb.virtual_ips[0].address):
                                get_vip = lb.virtual_ips[0].address
                        else:
                                get_vip = lb.virtual_ips[1].address
		domains = helper.act_loop(cdns.list, limit=1)
		for domain in domains:
                        dom = domain
                        dom_name = dom.name
                # create a cname for the container we created
                subdomain = '{0}.{1}'.format(lb_name, dom_name)
                recs = [{"type": "A", "name": subdomain, "data": get_vip, "ttl": 300}]
                # add our A record
                helper.act_loop(cdns.add_records, dom, recs)
                print 'created dns record: {0} -> {1} on domain: {2}'.format(subdomain, get_vip, dom_name)
                print "-------------------------------------"
                print "Load Balancer:", lb.name
                print "ID:", lb.id
                print "Status:", lb.status
                print "Nodes:", lb.nodes
                print "Virtual IPs:", lb.virtual_ips
                print "Algorithm:", lb.algorithm
                print "Protocol:", lb.protocol
                break
