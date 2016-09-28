import random
import string

from shutit_module import ShutItModule

class shutit_cookbook_openshiftv3(ShutItModule):


	def build(self, shutit):
		vagrant_image = shutit.cfg[self.module_id]['vagrant_image']
		vagrant_provider = shutit.cfg[self.module_id]['vagrant_provider']
		gui = shutit.cfg[self.module_id]['gui']
		memory = shutit.cfg[self.module_id]['memory']
		module_name = 'shutit_cookbook_openshiftv3_' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(6))
		shutit.send('rm -rf /tmp/' + module_name + ' && mkdir -p /tmp/' + module_name + ' && cd /tmp/' + module_name)
		shutit.send('vagrant init ' + vagrant_image)
		shutit.send_file('/tmp/' + module_name + '/Vagrantfile','''
Vagrant.configure(2) do |config|
  config.vm.box = "''' + vagrant_image + '''"
  # config.vm.box_check_update = false
  # config.vm.network "forwarded_port", guest: 80, host: 8080
  # config.vm.network "private_network", ip: "192.168.33.10"
  # config.vm.network "public_network"
  # config.vm.synced_folder "../data", "/vagrant_data"
  config.vm.provider "virtualbox" do |vb|
    vb.gui = ''' + gui + '''
    vb.memory = "''' + memory + '''"
    vb.name = "shutit_cookbook_openshiftv3"
  end
end''')
		shutit.send('vagrant up --provider virtualbox',timeout=99999)
		shutit.login(command='vagrant ssh')
		shutit.login(command='sudo su -',password='vagrant')

#############################################################
## This installer is suitable for a standalone installation #
## "All in the box" (Master and Node in a server)           #
#############################################################
#IP_DETECT=$(ip route get 8.8.8.8 | awk 'NR==1 {print $NF}')
#if [ -z $IP ] 
#then IP=$IP_DETECT
#fi
		ip_detected = shutit.send_and_get_output('''ip route get 8.8.8.8 | awk 'NR==1 {print $NF}' ''')
#read -p "Please enter the FQDN of the server: " FQDN
#read -p "Please enter the IP of the server (Auto Detect): $IP_DETECT" IP
		fqdn = 'localhost'
		if shutit.cfg[self.module_id]['deployment_type'] not in ('rpm','container'):
			shutit.fail('Wrong deployment type: ' + shutit.cfg[self.module_id]['deployment_type'])
		shutit.send('''sed -i "/''' + ip_detected + '''/d" /etc/hosts''')
		shutit.send('''echo -e "''' + ip_detected + r'''\t''' + fqdn + '''" >> /etc/hosts''')
#hostnamectl set-hostname $FQDN
		shutit.send('''hostnamectl set-hostname ''' + fqdn)
#systemctl restart systemd-hostnamed.service
		shutit.send('''systemctl restart systemd-hostnamed.service''')
		shutit.send('''yum -y update -q -e 0''')
		shutit.send('''mkdir -p ~/chef-solo-example/{backup,cache,roles,cookbooks,environments}''')
		shutit.send('''cd ~/chef-solo-example/cookbooks''')
		shutit.send('yum -y install -q https://packages.chef.io/stable/el/7/chef-12.13.37-1.el7.x86_64.rpm git')
		#### Installing cookbooks
		shutit.send('git clone -q https://github.com/IshentRas/cookbook-openshift3.git')
		shutit.send('git clone -q https://github.com/chef-cookbooks/iptables.git')
		shutit.send('git clone -q https://github.com/chef-cookbooks/yum.git')
		# Specific version seems to be required, else yum issues? see: issue #20
		shutit.send('git clone https://github.com/BackSlasher/chef-selinuxpolicy.git selinux_policy')
		shutit.send('cd selinux_policy')
		shutit.send('git checkout v0.9.2')
		shutit.send('cd ..')
		# Seems to be required? see: issue #20
		shutit.send('git clone -q https://github.com/chef-cookbooks/compat_resource')
		shutit.send('cd ~/chef-solo-example')
		#### Create the dedicated environment for Origin deployment
		if shutit.cfg[self.module_id]['deployment_type'] == 'rpm':
			deploy_containerized = 'false'
		else:
			deploy_containerized = 'true'
			
		shutit.send('''cat << EOF > environments/origin.json
{
  "name": "origin",
  "description": "",
  "cookbook_versions": {

  },
  "json_class": "Chef::Environment",
  "chef_type": "environment",
  "default_attributes": {

  },
  "override_attributes": {
    "cookbook-openshift3": {
      "openshift_common_public_hostname": "console.''' + ip_detected + '''.nip.io",
      "openshift_deployment_type": "origin",
      "deploy_containerized": ''' + deploy_containerized + ''',
      "master_servers": [
        {
          "fqdn": "''' + fqdn + '''",
          "ipaddress": "''' + ip_detected + '''"
        }
      ],
      "node_servers": [
        {
          "fqdn": "''' + fqdn + '''",
          "ipaddress": "''' + ip_detected + '''"
        }
      ]
    }
  }
}
EOF''')

		#### Specify the configuration details for chef-solo
		shutit.send('''cat << EOF > ~/chef-solo-example/solo.rb
cookbook_path [
               '/root/chef-solo-example/cookbooks',
               '/root/chef-solo-example/site-cookbooks'
              ]
environment_path '/root/chef-solo-example/environments'
file_backup_path '/root/chef-solo-example/backup'
file_cache_path '/root/chef-solo-example/cache'
log_location STDOUT
solo true
EOF''')
		#### Deploy OSE !!!!
		shutit.send('chef-solo --environment origin -o recipe[cookbook-openshift3],recipe[cookbook-openshift3::master],recipe[cookbook-openshift3::node] -c ~/chef-solo-example/solo.rb')
		shutit.send('''if ! $(oc get project test --config=/etc/origin/master/admin.kubeconfig &> /dev/null)
then 
  # Create a demo project
  oadm new-project demo --display-name="Origin Demo Project" --admin=demo
  # Set password for user demo
fi''')
		## Reset password for demo user
		shutit.send('htpasswd -b /etc/origin/openshift-passwd demo 1234')
		## Label the node as infra
		shutit.send('oc label node ' + fqdn + ' region=infra --config=/etc/origin/master/admin.kubeconfig &> /dev/null')
		# 'test'
		shutit.send('oc get all')
#		shutit.pause_point('''
####### Installation DONE ######
######                   ######
#Your installation of Origin is completed.
#
#A demo user has been created for you.
#Password is : 1234
#
#Access the console here : https://console.${IP}.nip.io:8443/console
#
#You can also login via CLI : oc login -u demo
#
#Next steps for you (To be performed as system:admin --> oc login -u system:admin):
#
#1) Deploy registry -> oadm registry --service-account=registry --credentials=/etc/origin/master/openshift-registry.kubeconfig --config=/etc/origin/master/admin.kubeconfig
#2) Deploy router -> oadm router --service-account=router --credentials=/etc/origin/master/openshift-router.kubeconfig
#3) Read the documentation : https://docs.openshift.org/latest/welcome/index.html
#
#You should disconnect and reconnect so as to get the benefit of bash-completion on commands''')

		shutit.logout()
		shutit.logout()
		return True

	def get_config(self, shutit):
		shutit.get_config(self.module_id,'vagrant_image',default='boxcutter/centos72')
		shutit.get_config(self.module_id,'vagrant_provider',default='virtualbox')
		shutit.get_config(self.module_id,'gui',default='false')
		shutit.get_config(self.module_id,'memory',default='1024')
		shutit.get_config(self.module_id,'deployment_type',default='rpm')
		return True

	def test(self, shutit):

		return True

	def finalize(self, shutit):

		return True

	def isinstalled(self, shutit):

		return False

	def start(self, shutit):

		return True

	def stop(self, shutit):

		return True

def module():
	return shutit_cookbook_openshiftv3(
		'imiell.shutit_cookbook_openshiftv3.shutit_cookbook_openshiftv3', 731503123.0001,   
		description='',
		maintainer='',
		delivery_methods=['bash'],
		depends=['shutit.tk.setup','shutit-library.virtualbox.virtualbox.virtualbox','tk.shutit.vagrant.vagrant.vagrant']
	)
