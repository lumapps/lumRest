import yaml, json

def expr_constructor(loader, node):
    """
    Surround the node with {{ }} so that we handle it as an expression
    """
    return "{{" + loader.construct_python_str(node) + "}}"

def json_constructor(loader, node):
    """
    Creates a json object
    """
    return json.loads(loader.construct_yaml_str(node))

    
