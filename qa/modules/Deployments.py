import os
import sys
from time import sleep
from chef import autoconfigure
from modules.razor_api import razor_api
from modules.Config import Config
from modules.Environments import Chef
from modules.Nodes import ChefRazorNode


"""
OpenStack deployments
"""


class Deployment(object):
    """Base for OpenStack deployments"""
    def __init__(self, name, os_name, branch, features=[]):
        self.name = name
        self.os = os_name
        self.features = features
        self.nodes = []

    def destroy(self):
        """ Destroys an OpenStack deployment """
        for node in self.nodes:
            node.destroy()

    def create_node(self, role):
        """ Abstract node creation method """
        raise NotImplementedError

    def provision(self):
        """Provisions nodes for each desired feature"""

    def pre_configure(self):
        """Pre configures node for each feature"""
        for feature in self.features:
            feature.pre_configure(self)

    def build_nodes(self):
        """Builds each node"""
        for node in self.nodes:
            node.build()

    def post_configure(self):
        """Post configures node for each feature"""
        for feature in self.features:
            feature.post_configure(self)

    def build(self):
        """Runs build steps for node's features"""
        self.update_environment()
        self.pre_configure()
        self.build_nodes()
        self.pre_configure()


class ChefRazorDeployment(Deployment):
    """
    Deployment mechinisms specific to deployment using:
    Puppet's Razor as provisioner and
    Opscode's Chef as configuration management
    """
    def __init__(self, name, os_name, branch, features, chef, razor):
        super(ChefRazorDeployment, self).__init__(name, os_name, branch,
                                                  features)
        self.chef = chef
        self.razor = razor
        self.environment = None

    @classmethod
    def free_node(cls, image):
        """
        Provides a free node from
        """
        in_image_pool = "name:qa-%s-pool*" % image
        is_default_environment = "chef_environment:_default"
        is_ifaced = """run_list:recipe\[network-interfaces\]"""
        query = "%s AND %s AND %s" % (in_image_pool,
                                      is_default_environment,
                                      is_ifaced)
        # TODO: Add node_search to chef helper
        nodes = Chef.node_search(query)
        fails = 0
        try:
            node = next(nodes)
            node['in_use'] = "provisioned"
            nodes.save
            yield node
        except StopIteration:
            if fails > 10:
                print "No available chef nodes"
                sys.exit(1)
            fails += 1
            sleep(15)
            # TODO: Add node_search to chef helper
            nodes = Chef.node_search(query)

    @classmethod
    def fromfile(cls, name, branch, config, path=None):
        if not path:
            path = os.path.join(os.path.dirname(__file__),
                                os.pardir,
                                'deployment_templates/default.yaml')
        template = Config(path)[name]
        local_api = autoconfigure()
        chef = Chef(name, local_api, description=name)
        razor = razor_api(config['razor']['ip'])
        os_name = template['os']
        product = template['product']
        deployment = cls(template['name'], os_name, branch,
                         template['features'], chef, razor)
        for node_features in template['nodes']:
            node = ChefRazorNode(cls.free_node(os_name).name, os_name, product,
                                 chef, deployment, razor, branch,
                                 node_features)
            deployment.nodes.append(node)
        return deployment

    def search_role(self, feature):
        """Returns nodes the have the desired role"""
        return (node for node in self.nodes if feature in node.features)

    def destroy(self):
        super(ChefRazorDeployment, self).destroy()
        # TODO: Add destroy to a chef helper class
        self.environment.destroy()