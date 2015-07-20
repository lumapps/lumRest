import traceback
import os
import json
import re
import time
import apiclient
from jsonpath import jsonpath
import utils as ju
from utils import pretty_json, check_json
from app.oauth import OAuth

def get_service(service_config, auth_config=None, provider="GOOGLE"):
    if provider == "GOOGLE":
        if auth_config:
            return OAuth.getService(auth_config['email'],
                                    service_config['api'],
                                    service_config['version'],
                                    auth_config['oauth_scope'],
                                    auth_config['client_secret'],
                                    auth_config['client_id'],
                                    discoveryUrl=service_config['discovery_url'])
        else:
            return apiclient.discovery.build(service_config['api'], service_config['version'],
                                            discoveryServiceUrl=service_config['discovery_url'])

class CommandParser():
    """
    The Parser class
    """

    def __init__(self, config, scene, scene_root, exit_on_error=False):
        self.output_results = {}
        self.expression_matcher = re.compile("{{([^{}]*)}}")
        self.scenario = scene
        self.scenario_root = scene_root
        self.config = config
        self.exit_on_error = exit_on_error

        if 'debug' in self.config:
            self.debug = self.config['debug']
        else:
            self.debug = False

        # authenticate
        self.service = get_service(scene['service'], config.get('auth', None))

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
        - `check_result`: given a json file, uses `json_utils.check_json()`
            to check that the result respects its pattern.
        """
        print "Running scenario {}".format(self.scenario.get('name', self.scenario_root))

        if 'commands' not in self.scenario:
            raise ValueError("The scenario file has to contain a `commands` section")

        commands = self.scenario['commands']
        error = False
        for command in commands:
            try:
                if isinstance(command, unicode) or isinstance(command, str):
                    command = {command:[]}

                service = self.service
                # change the auth temporarily
                if 'config' in command:
                    config = self.config
                    service_config = self.scenario['service']
                    if 'auth' in command['config']:
                        for key, val in command['config']['auth'].iteritems():
                            config['auth'][key] = self.eval_expr(val)

                    if 'service' in command['config']:
                        for key, val in command['config']['service'].iteritems():
                            service_config[key] = self.eval_expr(val)

                    service = get_service(service_config, config.get('auth', None))
                    command.pop('config')

                self.__parse_command(command, service, self.scenario_root)
            except AssertionError:
                error = True
            except Exception, e:
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
        export_result = None
        eval_expr = None
        pre_eval_expr = None
        check_code = 200
        check_message = None
        repeat_while = None
        repeat_delay = 1
        repeat = None
        description = None

        # load the check_result json file if provided
        if 'check_result' in command:
            check_json_val = command.pop('check_result')
            if isinstance(check_json_val, dict):
                json_pattern = check_json_val
            elif isinstance(check_json_val, str) or isinstance(check_json_val, unicode):
                check_json_file = os.path.join(scenario_root, check_json_val)

                # check that there is a check file
                if not os.path.isfile(check_json_file):
                    raise ValueError("{} does not exist".format(check_json_file))

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

        if len(command.keys()) != 1:
            raise ValueError("You must provide one and only one endpoint per command, see the manual.\n{}".format(
                "\n".join(['- {}'.format(k) for k in command])))

        # build the endpoint request
        key = command.keys()[0]

        # import pdb; pdb.set_trace()
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
                                body_file = os.path.join(scenario_root, val)
                                if not os.path.isfile(body_file):
                                    print "{} does not exist".format(body_file)
                                    continue

                                with open(body_file, 'r') as body:
                                    val = json.load(body)

                        # parse expressions in the body
                        val = self._parse_body(val)

                        # avoid to use `self.eval_expr` in the yml by using `expr` directly
                        expr = lambda e: self.eval_expr('{{' + e + '}}')

                        ns = {'saved_results': self.output_results, 'body': val, 'expr': lambda e: self.eval_expr('{{' + e + '}}')}

                        if pre_eval_expr:
                            if isinstance(pre_eval_expr, str) or isinstance(pre_eval_expr, unicode):
                                exec pre_eval_expr in ns
                            elif isinstance(pre_eval_expr, list):
                                for e in pre_eval_expr:
                                    exec e in ns

                        val = ns.get('body', val)

                    else:
                        if isinstance(val, str) or isinstance(val, unicode):
                            val = '"' + str(self.eval_expr(val)) + '"'

                    endpoint_args.append("{} = {}".format(arg, val))

            endpoint += ','.join(endpoint_args) + ').execute()'

            print "\n{}{}Executing : {}{}".format(ju.bold, ju.yellow, key, ju.end_color)
            if description:
                print "Description: {}\n".format(description)

            exec_time = time.time()
            # run the endpoint request
            status = 200
            message = None
            try:
                result = eval(endpoint)
            except Exception, e:
                try:
                    message = json.loads(e.content).get('error').get('message')
                except:
                    pass

                if check_code and hasattr(e, 'resp') and e.resp["status"] == str(check_code):
                    status = check_code
                else:
                    if len(e.message) == 0:
                        msg = e.__str__()
                    else:
                        msg = e.message
                    raise RuntimeError("The executed command was: {}\nMessage: {}".
                                       format(endpoint.replace("\.execute()", ""), msg))
            print "Done in {}ms".format(int(round((time.time() - exec_time) * 1000)))

            skip_results = False
            if status != check_code:
                raise RuntimeError("The executed command was: {}\nMessage: {}".format(
                    endpoint.replace("\.execute()", ""),
                    "HTTP status code is {} and expected is {}.".format(status, check_code)
                ))
            elif int(check_code) - 200 >= 100:
                skip_results = True
                result = None

            if check_message and check_message != message:
                raise RuntimeError("The executed command was: {}\nMessage: {}".format(
                    endpoint.replace("\.execute()", ""),
                    "HTTP error message is {} and expected is {}.".format(message, check_message)
                ))

            if eval_expr and not skip_results:
                ns = {'saved_results': self.output_results, 'result': result, 'expr': lambda e: self.eval_expr('{{'+e+'}}')}

                if isinstance(eval_expr, str) or isinstance(eval_expr, unicode):
                    exec eval_expr in ns
                elif isinstance(eval_expr, list):
                    for e in eval_expr:
                        exec e in ns

                result = ns.get('result', result)

            if result_name and not skip_results:
                self.output_results[result_name] = result

            if export_result and not skip_results:
                with open("{}".format(export_result), 'w') as f:
                    json.dump(result, f, indent=4, separators=(',', ': '))

            if not skip_results:
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
                        except Exception, e:
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
                            try:
                                val = self.__parse_expression(match.group(1), container=result)
                            except Exception, e:
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

    def _parse_body(self, body):
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
                self._parse_body(val)
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
            mode: until|while (default: while)
            delay: <float> (default: 1)
            max: <int> (default: 5)
            conditions:
                code: <int> (default: 200)
                message: <str>
                expression: <str> (python expression)
        """
        mode = repeat.get('mode', 'until')
        delay = repeat.get('delay', 1.0)
        maximum = repeat.get('max', 5)
        conditions = repeat.get('conditions', {'code': 200, 'message': None, 'expression': None})
        code = conditions.get('code', 200)
        message = conditions.get('message', None)
        expression = conditions.get('expression', None)

        if maximum != 0 and times > maximum:
            return False

        cont = True
        ns = {'saved_results': self.output_results, 'result': result, 'expr': lambda e: self.eval_expr('{{'+e+'}}')}
        
        check = lambda l, r: l == r if mode == 'while' else l != r

        if code and not check(code, status):
            return False
        if message and not check(message, msg):
            return False

        if isinstance(expression, str) or isinstance(expression, unicode):
            exec 'expression = ({})'.format(expression) in ns
            cont = ns['expression']
        elif isinstance(expression, list):
            if mode == 'while':
                cont = True
                for e in expression:
                    exec 'expression = ({})'.format(expression) in ns
                    cont = cont and ns['expression']
            else:
                cont = False
                for e in expression:
                    exec 'expression = ({})'.format(expression) in ns
                    cont = cont or ns['expression']
        if not cont:
            return False

        time.sleep(delay)
        return True

    def eval_expr(self, val):
        match = self.expression_matcher.match(val)
        if match:
            # raises a ValueError, to be catched upper in the stack
            val = self.__parse_expression(match.group(1))
        return val
