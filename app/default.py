import subprocess
import traceback
import os
import sys
import json
import re
import yaml
import time
import apiclient

from httplib import BadStatusLine

from httplib2 import Http
from apiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials

from app.utils import check_order_values
from jsonpath import jsonpath
import utils as ju
from utils import pretty_json, check_json


__version__ = '0.111'


def get_service(service_config, auth_config=None, provider="GOOGLE"):
    if provider == "GOOGLE":
        if auth_config:
            credentials = ServiceAccountCredentials.from_p12_keyfile(
                auth_config['client_id'], auth_config['client_secret'],
                scopes=auth_config['oauth_scope']
            )
            if 'email' in auth_config:
                delegated_credentials = credentials.create_delegated(auth_config['email'])
                http_auth = delegated_credentials.authorize(Http())
            else:
                http_auth = credentials.authorize(Http())

            build_optional_cfg = {'http': http_auth, 'cache_discovery': False}
            if service_config['discovery_url']:
                build_optional_cfg['discoveryServiceUrl'] = service_config['discovery_url']

            service = build(service_config['api'], service_config['version'], **build_optional_cfg)
            return service
        else:
            return build(service_config['api'], service_config['version'],
                         discoveryServiceUrl=service_config['discovery_url'], cache_discovery=False)


class CommandParser():
    """
    The Parser class
    """
    _foundpaths = []
    def get_filepath(self, scene_root, path, strict=True):
        paths = [re.sub(r'^\./', scene_root, path), os.path.abspath(path), os.path.abspath(os.path.join(scene_root, path))]
        paths.extend([os.path.abspath(os.path.join(folder, path)) for folder in self._foundpaths])
        for path in paths:
            if os.path.isfile(path):
                # we don't keep track of the file where the command is kept
                # thus we need an hack to keep track of the found files which could reference it
                # !!! the resulting path could be ambiguous
                _, ext = os.path.splitext(path)
                if ext == '.yaml':
                    self._foundpaths.append(os.path.dirname(path))
                return path
        if strict:
            raise RuntimeError("{} cannot be found in any of the hintpaths ({})".format(path, paths))

    def __init__(self, config, scene, scene_root, exit_on_error=False):
        self.output_results = {}
        self.expression_matcher = re.compile("{{([^{}]*)}}")
        self.scenario = scene
        self.scenario_root = scene_root
        self.config = dict(config)
        self.exit_on_error = exit_on_error
        self.hooks = {
            "setup": None,
            "teardown": None,
        }
        self.imports = []
        self.setup_commands = []

        if 'debug' in self.config:
            self.debug = self.config['debug']
        else:
            self.debug = False

        if scene.get('skip', False):
            sys.exit(0)

        if 'commands' not in scene:
            scene['commands'] = []

        # authenticate
        self.service = get_service(scene['service'], config.get('auth', None))

        if 'hooks' in scene:
            hooks = scene['hooks']
            if not isinstance(hooks, dict):
                raise ValueError("Hooks must be a dict")

            self.hooks["setup"] = hooks.get("setup")
            self.hooks["teardown"] = hooks.get("teardown")

        # if we have setup includes, prepend them
        if 'setup' in scene:
            setup = scene['setup']
            if isinstance(setup, str) or isinstance(setup, unicode):
                setup = [setup]

            if not isinstance(setup, list):
                raise ValueError("Setup must be either a list of filenames or a single filename")

            for setup_file in setup:
                setup_file = self.get_filepath(scene_root, setup_file)

                with open(setup_file, 'r') as f:
                    f_content = f.read()
                    f_content = re.sub(r'(\s+body:\s*)\.\/(.*json)',
                                       r'\1{}/\2'.format(os.path.split(os.path.abspath(setup_file))[0]), f_content)
                    setup_yml = yaml.load(f_content)

                    if 'commands' in setup_yml:
                        self.setup_commands.extend(setup_yml['commands'])

        if 'import' in scene:
            imports = scene['import']
            if isinstance(imports, str) or isinstance(imports, unicode):
                imports = [imports]

            if not isinstance(imports, list):
                raise ValueError("Imports must be either a list of filenames or a single filename")

            for import_file in imports:
                import_file = self.get_filepath(scene_root, import_file)

                with open(import_file, 'r') as f:
                    f_content = f.read()
                    f_content = re.sub(r'(\s+body:\s*)\.\/(.*json)',
                                       r'\1{}/\2'.format(os.path.split(os.path.abspath(import_file))[0]), f_content)
                    setup_yml = yaml.load(f_content)
                    self.imports.append(
                        CommandParser(config, setup_yml, self.scenario_root, exit_on_error=exit_on_error))

        # if we have teardown includes, append them
        if 'teardown' in scene:
            teardown = scene['teardown']
            if isinstance(teardown, str) or isinstance(teardown, unicode):
                teardown = [teardown]

            if not isinstance(teardown, list):
                raise ValueError("teardown must be either a list of filenames or a single filename")

            for teardown_file in teardown:
                teardown_file = self.get_filepath(scene_root, teardown_file)

                with open(teardown_file, 'r') as f:
                    teardown_yml = yaml.load(f)

                    if 'commands' in teardown_yml:
                        scene['commands'].extend(teardown_yml['commands'])

    def parse(self):
        """
        Run the commands in the scenario

        Using the yaml file, ``scenario.yaml``, the commands are listed under the
        key commands:
        ```yaml
        commands:
            - endpointname.op:
                arg1 : val1
                arg2 : val2
              save_result: result_name
            - endpointname.op2:
                arg1 : val1
                arg2 : val2
              save_result: result_name2
              check_result: output_template.json
        ```

        The possible keys to be used for each key are:

        - The mandatory endpoint name, its value is a dictionary of arguments
            and their respective values.
        - `save_result`: saves the result of this endpoint into a dictionary.
            Its value is the name used to reference it.
        - `print_result`: outputs the result of this endpoint execution to stdout
        - `print_body`: output the json sent to the endpoint
        - `check_result`: given a json file, uses `json_utils.check_json()`
            to check that the result respects its pattern.

        Return a boolean (True if an error occurred, else False)
        """
        if self.hooks.get("setup"):
            self.run_hook(self.hooks["setup"], "setup")

        print "Running scenario {} setup".format(self.scenario.get('name', self.scenario_root))

        error = self.__parse_commands(self.setup_commands)
        if error and self.exit_on_error:
            return error

        for import_scenario in self.imports:
            print "Import scenario {}".format(import_scenario.scenario.get('name', import_scenario.scenario_root))
            if import_scenario.parse() and import_scenario.exit_on_error:
                return True

        print "Running scenario {} commands".format(self.scenario.get('name', self.scenario_root))

        error = self.__parse_commands(self.scenario.get('commands', []))
        if error and self.exit_on_error:
            return error

        if self.hooks.get("teardown"):
            self.run_hook(self.hooks["teardown"], "teardown")

        return error

    def __parse_commands(self, commands):
        """
        Execute a list of commands.
        If an error occurred, and exit_on_error is set to True, error code will immediately be returned.

        Args:
            commands: the list of commands to execute
        Returns:
            True if an error occurred, else False.
        """
        error = False
        for command in commands:
            try:
                if isinstance(command, unicode) or isinstance(command, str):
                    command = {command: []}

                service = self.service
                # change the auth temporarily
                if 'config' in command:
                    config = dict(self.config)
                    service_config = self.scenario['service']
                    if 'auth' in command['config']:
                        if command['config']['auth']:
                            for key, val in command['config']['auth'].iteritems():
                                if isinstance(val, unicode) or isinstance(val, str):
                                    config['auth'][key] = self.eval_expr(val)
                                else:
                                    config['auth'][key] = val
                        else:
                            config['auth'] = None

                    if 'service' in command['config']:
                        for key, val in command['config']['service'].iteritems():
                            service_config[key] = self.eval_expr(val)

                    service = get_service(service_config, config.get('auth', None))
                    command.pop('config')

                delay = None
                if 'post_delay' in command:
                    delay = command.pop('post_delay')

                self.__parse_command(command, service, self.scenario_root)

                if delay:
                    print "Wait {} seconds".format(delay)
                    time.sleep(delay)
            except AssertionError:
                error = True
            except Exception as e:
                print "{}{}Unable to execute command:{} {}{}{}\n{}{}{}\n".format(
                    ju.error_color, ju.bold, ju.end_color,
                    ju.error_color_detail, command.keys()[0],
                    ju.error_color, ju.bold, e, ju.end_color)
                print traceback.format_exc()
                error = True
            finally:
                if error and self.exit_on_error:
                    return error

        return error

    def __parse_command(self, command, service, scenario_root):
        json_pattern = None
        result_name = None
        print_result = False
        print_body = False
        export_result = None
        eval_expr = None
        pre_eval_expr = None
        check_code = 200
        check_message = None
        repeat = None
        description = None
        order = None
        hooks = None
        body_to_print = False

        # load the check_result json file if provided
        if 'check_result' in command:
            check_json_val = command.pop('check_result')
            if isinstance(check_json_val, dict):
                json_pattern = check_json_val
            elif isinstance(check_json_val, str) or isinstance(check_json_val, unicode):
                check_json_file = self.get_filepath(self.scenario_root, check_json_val)

                with open(check_json_file, 'r') as check:
                    json_pattern = json.load(check)

        if 'save_result' in command:
            result_name = command.pop('save_result')

        if 'check_code' in command:
            check_code = command.pop('check_code')

        if 'check_message' in command:
            check_message = command.pop('check_message')

        if 'print_result' in command:
            print_result = command.pop('print_result')

        if 'print_body' in command:
            print_body = command.pop('print_body')

        if 'export_result' in command:
            export_result = command.pop('export_result')

        if 'eval_expr' in command:
            eval_expr = command.pop('eval_expr')

        if 'pre_eval_expr' in command:
            pre_eval_expr = command.pop('pre_eval_expr')

        if 'repeat' in command:
            repeat = command.pop('repeat')

        if 'description' in command:
            description = unicode(command.pop('description'))

        if 'check_order' in command:
            order = command.pop('check_order')

        if 'hooks' in command:
            hooks = command.pop('hooks')

        if len(command.keys()) != 1:
            raise ValueError("You must provide one and only one endpoint per command, see the manual.\n{}".format(
                "\n".join(['- {}'.format(k) for k in command])))

        # build the endpoint request
        key = command.keys()[0]

        if hooks and "setup" in hooks:
            self.run_hook(hooks.get("setup"), "setup")

        repeat_bool = True
        times = 0

        while repeat_bool:
            # put the () for the endpoints
            endpoint = 'service.' + key.replace('.', '().')
            endpoint += '('

            endpoint_args = []
            if isinstance(command[key], dict):
                for arg in command[key]:
                    val = command[key][arg]

                    # for body, read the json file
                    if arg == 'body':
                        # if we do not receive a json object, load it from a file
                        if not isinstance(val, dict):
                            match = self.expression_matcher.match(val)
                            if match:
                                # raises a ValueError, to be catched upper in the stack
                                val = self.__parse_expression(match.group(1))
                            else:
                                body_file = self.get_filepath(self.scenario_root, val)

                                if body_file:
                                    with open(body_file, 'r') as body:
                                        val = json.load(body)

                        # parse expressions in the body
                        val = self._parse_body(val)

                        # avoid to use `self.eval_expr` in the yml by using `expr` directly
                        expr = lambda e: self.eval_expr('{{' + e + '}}')

                        saved_results = self.output_results
                        saved_results['body'] = val
                        ns = {'saved_results': saved_results,
                              'body': val,
                              'expr': lambda e: self.eval_expr('{{' + e + '}}', container=saved_results)}

                        if pre_eval_expr:
                            if isinstance(pre_eval_expr, str) or isinstance(pre_eval_expr, unicode):
                                exec pre_eval_expr in ns
                            elif isinstance(pre_eval_expr, list):
                                for e in pre_eval_expr:
                                    exec e in ns

                        val = ns.get('body', val)
                        if print_body is True:
                            body_to_print = val
                    else:
                        if isinstance(val, basestring):
                            val = '"' + str(self.eval_expr(val)) + '"'
                        elif isinstance(val, list):
                            # if we have a list here, we want to transform it into arg=[val1,val2]
                            # resolving each element of the list
                            val = ','.join([str(self.eval_expr(v)) for v in val])
                            val = "[{}]".format(val)

                    endpoint_args.append("{} = {}".format(arg, val))

            endpoint += ','.join(endpoint_args) + ').execute()'

            print "\n{}{}Executing : {}{}".format(ju.bold, ju.yellow, key, ju.end_color)
            if description:
                print "Description: {}\n".format(description)

            if body_to_print:
                print ju.info_color
                print "Body JSON:"
                pretty_json(body_to_print)
                print ju.end_color

            exec_time = time.time()
            # run the endpoint request
            status = 200
            message = None
            result = None

            retry = True
            nb_retries = 5
            while retry and nb_retries > 0:
                nb_retries -= 1
                try:
                    ns = {'service': service}
                    exec "result = {}".format(endpoint) in ns
                    result = ns['result']
                    retry = False
                except BadStatusLine as e:
                    print "RETRYING: {}".format(endpoint)
                    retry = True
                    time.sleep(1)
                except Exception as e:
                    retry = False
                    try:
                        message = json.loads(e.content).get('error').get('message')
                    except:
                        pass

                    if check_code and hasattr(e, 'resp') and e.resp["status"] == str(check_code):
                        status = check_code
                    elif not repeat:
                        if len(e.message) == 0:
                            msg = e.__str__()
                        else:
                            msg = e.message
                        print traceback.format_exc()
                        raise RuntimeError("The executed command was: {}\nMessage: {}".
                                           format(endpoint.replace("\.execute()", ""), msg))
                    else:
                        if hasattr(e, 'resp'):
                            status = e.resp["status"]
                        result = None
            print "Done in {}ms".format(int(round((time.time() - exec_time) * 1000)))

            if not repeat and status != check_code:
                raise RuntimeError("The executed command was: {}\nMessage: {}".format(
                    endpoint.replace("\.execute()", ""),
                    "HTTP status code is {} and expected is {}.".format(status, check_code)
                ))
            elif not repeat and int(check_code) - 200 >= 100:
                result = None

            if check_message and check_message != message:
                raise RuntimeError("The executed command was: {}\nMessage: {}".format(
                    endpoint.replace("\.execute()", ""),
                    "HTTP error message is {} and expected is {}.".format(message, check_message)
                ))

            if eval_expr:
                ns = {'saved_results': self.output_results,
                      'result': result,
                      'expr': lambda e, container=self.output_results: self.eval_expr('{{' + e + '}}', container)}

                if isinstance(eval_expr, str) or isinstance(eval_expr, unicode):
                    exec eval_expr in ns
                elif isinstance(eval_expr, list):
                    for e in eval_expr:
                        exec e in ns

                result = ns.get('result', result)

            if result_name and result:
                self.output_results[result_name] = result

            if export_result and result:
                with open("{}".format(export_result), 'w') as f:
                    json.dump(result, f, indent=4, separators=(',', ': '))

            if result:
                if print_result is True:
                    print ju.info_color
                    print "Result JSON:"
                    pretty_json(result)
                    print ju.end_color
                elif isinstance(print_result, str) or isinstance(print_result, unicode):
                    # we have an expression!
                    match = self.expression_matcher.match(print_result)
                    if match:
                        val = None
                        try:
                            val = self.__parse_expression(match.group(1), container=result)
                        except Exception as e:
                            if self.debug:
                                print traceback.format_exc()
                            print e

                        if val:
                            print ju.info_color
                            print "Content of {}:".format(match.group(1))
                            pretty_json(val)
                            print ju.end_color
                elif isinstance(print_result, list):
                    for expr in print_result:
                        # we have an expression!
                        match = self.expression_matcher.match(expr)
                        if match:
                            val = None
                            try:
                                val = self.__parse_expression(match.group(1), container=result)
                            except Exception as e:
                                if self.debug:
                                    print traceback.format_exc()
                                print e

                            if val:
                                print ju.info_color
                                print "Content of {}:".format(match.group(1))
                                pretty_json(val)
                                print ju.end_color
                            val = None

            if repeat:
                repeat_bool = self.__parse_repeat(repeat, times, result, status, message)
                if repeat_bool:
                    print "Calling the endpoint again"
                else:
                    print "Done repeating the call"
                times += 1
            else:
                repeat_bool = False

            if json_pattern:
                json_pattern = self._parse_body(json_pattern)
                check_json(result, json_pattern, exit_on_error=self.exit_on_error)

            if order:
                if isinstance(order, str) or isinstance(order, unicode):
                    match = self.expression_matcher.match(order)
                    raise RuntimeError("Expression {} for check_order is incorrect".format(match.group(1)))

                elif isinstance(order, list):
                    values = []
                    directions = []
                    paths = []
                    for criteria in order:
                        for expr, direction in criteria.iteritems():
                            # we have a list!
                            match = self.expression_matcher.match(expr)
                            if match:
                                val = self.__parse_expression(match.group(1), container=result)
                                values.append(val)
                                directions.append(direction)
                                paths.append(match.group(1))

                    check_order_values(values, directions, paths, exit_on_error=self.exit_on_error)

        if hooks and "teardown" in hooks:
            self.run_hook(hooks.get("teardown"), "teardown")

    def _parse_body(self, body):
        body = dict(body)
        for key, val in body.iteritems():
            if isinstance(val, unicode) or isinstance(val, str):
                match = self.expression_matcher.match(val)
                if match:
                    val = self.__parse_expression(match.group(1))
                    body[key] = val
            elif isinstance(val, list):
                for idx, sub_val in enumerate(val):
                    if isinstance(sub_val, dict):
                        body[key][idx] = self._parse_body(sub_val)
                    elif isinstance(sub_val, unicode) or isinstance(sub_val, str):
                        match = self.expression_matcher.match(sub_val)
                        if match:
                            sub_val = self.__parse_expression(match.group(1))
                            body[key][idx] = sub_val
            elif isinstance(val, dict):
                body[key] = self._parse_body(val)
        return body

    def __parse_expression(self, expression, container=None):
        """
        Parses the jsonpath expression in {self.output_results} and return its result
        """
        if container is None:
            container = self.output_results

        expression = expression.strip()
        as_list = False

        if expression.endswith("as list"):
            as_list = True
            expression = expression.replace("as list", "").strip()

        try:
            results = jsonpath(container, expression)
        except Exception, e:
            print e
            raise RuntimeError("Error when parsing the expression {}".format(expression))

        if results is False or len(results) == 0:
            raise RuntimeError("The expression {} gave no result".format(expression))

        if as_list:
            return results
        else:
            return results[0]

    def __parse_repeat(self, repeat, times, result, status, msg):
        """
        parse repeat command:

        repeat:
            mode: until|while|loop (default: while)
            delay: <float> (default: 1)
            max: <int> (default: 5)
            conditions:
                code: <int> (default: 200)
                message: <str>
                expression: <str> (python expression)
                raise_exception: <bool> (default: false)
        """
        mode = repeat.get('mode', 'while')
        delay = repeat.get('delay', 1.0)
        maximum = repeat.get('max', 5)
        conditions = repeat.get('conditions', {'code': 200, 'message': None, 'expression': None})
        has_code = conditions.get('code') is not None
        code = conditions.get('code', 200)
        has_message = conditions.get('message') is not None
        message = conditions.get('message', None)
        expression = conditions.get('expression', None)
        raise_exception = conditions.get('raise_exception', False)

        if mode == 'loop':
            if maximum == 0:
                raise ValueError("Maximum cannot be set to zero when using loop mode")
            if times + 1 >= maximum:
                return False

        if maximum != 0 and times >= maximum:
            raise RuntimeError("Retried {} time(s) without success.".format(maximum))

        cont = True
        saved_results = self.output_results
        saved_results['result'] = result
        ns = {'saved_results': saved_results,
              'result': result,
              'expr': lambda e: self.eval_expr('{{' + e + '}}', container=saved_results)}

        def check(l, r):
            valid = l == r if mode in ['while', 'loop'] else l != r

            if mode == 'loop' and not valid and not raise_exception:
                valid = True  # continue 'loop' mode if bad value received and no raise_exception flag

            if raise_exception and not valid:
                raise RuntimeError("Repeat condition is expecting {}, received {}".format(l, r))
            else:
                return valid

        def check_bool(l):
            return check(True, l)

        if has_code and not check(code, status):
            return False
        if has_message and not check(message, msg):
            return False

        if isinstance(expression, str) or isinstance(expression, unicode):
            exec 'expression = ({})'.format(expression) in ns
            cont = check_bool(ns['expression'])
        elif isinstance(expression, list):
            if mode == 'while':
                cont = True
                for e in expression:
                    exec 'expression = ({})'.format(expression) in ns
                    cont = cont and ns['expression']
            elif mode == 'loop':
                cont = True
            else:
                cont = False
                for e in expression:
                    exec 'expression = ({})'.format(expression) in ns
                    cont = cont or not ns['expression']
        if not cont:
            return False

        time.sleep(delay)
        return True

    def eval_expr(self, val, container=None):
        match = self.expression_matcher.match(val)
        if match:
            # raises a ValueError, to be catched upper in the stack
            val = self.__parse_expression(match.group(1), container=container)
        return val

    def run_hook(self, command, kind='setup'):
        print "Running {} hook {}".format(command, kind)
        subprocess.call("./{}".format(command), shell=True)
