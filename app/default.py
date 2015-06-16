import logging, traceback, os, json, re, time, apiclient
from jsonpath import jsonpath
import utils as ju
from utils import pretty_json, check_json
from app.oauth import OAuth

class CommandParser():
    """
    The Parser class
    """

    def __init__(self, config, scene, scene_root):
        self.output_results = {}
        self.expression_matcher = re.compile("{{([^{}]*)}}")
        self.scenario = scene
        self.scenario_root = scene_root
        self.config = config

        if self.config.has_key('debug'):
            self.debug = self.config['debug']
        else:
            self.debug = False

        # authenticate
        if config.has_key('auth'):
            self.service = OAuth.getService(config['auth']['email'], scene['service']['api'],
                                       scene['service']['version'], config['auth']['oauth_scope'],
                                       config['auth']['client_secret'], config['auth']['client_id'],
                                       discoveryUrl = scene['service']['discovery_url'])
        else:
            self.service = apiclient.discovery.build(
                scene['service']['api'], scene['service']['version'],
                discoveryServiceUrl = scene['service']['discovery_url'])

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

        - The mandatory endpoint name, its value is a dictionary of arguments and their respective values.
        - `save_result`: saves the result of this endpoint into a dictionary. Its value is the name used to reference it.
        - `print_result`: outputs the result of this endpoint execution to stdout
        - `check_result`: given a json file, uses `json_utils.check_json()` to check that the result respects its pattern.
        """
        print "Running scenario {}".format(self.scenario.get('name', self.scenario_root))

        if not self.scenario.has_key('commands'):
            raise ValueError("The scenario file has to contain a `commands` section")

        commands = self.scenario['commands']
        error = False
        for command in commands:
            try:
                self.__parse_command(command, self.service, self.scenario_root)
            except Exception, e:
                print "{}{}Unable to execute command:{} {}{}{}\n{}{}{}\n"\
                  .format(ju.error_color, ju.bold, ju.end_color,
                          ju.error_color_detail, command.keys()[0],
                          ju.error_color, ju.bold, e, ju.end_color)
                if self.debug:
                    print traceback.format_exc()
                error = True
        return error

    def __parse_command(self, command, service, scenario_root):
        json_pattern = None
        result_name = None
        print_result = False
        export_result = None
        eval_expr = None
        repeat = 1
        repeatList = None

        if command.has_key('check_result'):
            check_json_val = command.pop('check_result')
            if isinstance(check_json_val, dict):
                json_pattern = check_json_val
            elif isinstance(check_json_val, str) or isinstance(check_json_val, unicode):
                check_json_file = os.path.join(scenario_root, check_json)

                # check that there is a check file
                if not os.path.isfile(check_json_file):
                    raise ValueError("{} does not exist".format(check_json_file))

                with open(check_json_file, 'r') as check:
                    json_pattern = json.load(check)

        if command.has_key('save_result'):
            result_name = command.pop('save_result')

        if command.has_key('print_result'):
            print_result = command.pop('print_result')

        if command.has_key('export_result'):
            export_result = command.pop('export_result')

        if command.has_key('eval_expr'):
            eval_expr = command.pop('eval_expr')

        if command.has_key('repeat'):
            repeat = command.pop('repeat')
            if isinstance(repeat, str) or isinstance(repeat, unicode):
                #todo: replace this with a jsonpath expression
                repeatFormat = repeat.split(".")
                repeatList = self.output_results
                for keyVal in repeatFormat:
                    repeatList = repeatList[keyVal]
                repeat = len(repeatList)

                #match = self.expression_matcher.match(repeat)
                #if match:
                    ## raises a ValueError, to be catched upper in the stack
                    #val = self.__parse_expression(match.group(1))
                #else:
                    #repeat = None

        if len(command.keys()) != 1:
            raise ValueError("You must provide one and only one endpoint per command, see the manual")

        # build the endpoint request
        key = command.keys()[0]

        #import pdb; pdb.set_trace()
        for i in xrange(repeat):
            # put the () for the endpoints
            endpoint = 'service.' + key.replace('.', '().')
            endpoint += '('

            endpoint_args = []
            if isinstance(command[key], dict):
                for arg in command[key]:
                    if repeat > 1:
                        #todo: replace this with a jsonpath expression
                        val = command[key][arg]
                        val, argKey = val.split('@')
                        repeatFormat = val.split(".")
                        #import pdb; pdb.set_trace()
                        tempList = self.output_results
                        for keyVal in repeatFormat:
                            tempList = tempList[keyVal]
                        val = tempList[i][argKey]
                    else:
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
                    else:
                        if isinstance(val, str) or isinstance(val, unicode):
                            # if we have a variable name check in the output_results
                            match = self.expression_matcher.match(val)
                            if match:
                                # raises a ValueError, to be catched upper in the stack
                                val = self.__parse_expression(match.group(1))

                            val = '"' + str(val) + '"'

                    endpoint_args.append("{} = {}".format(arg, val))

            endpoint += ','.join(endpoint_args) + ').execute()'

            print "\n{}{}Executing : {}{}".format(ju.bold, ju.yellow, key, ju.end_color)

            exec_time = time.time()
            # run the endpoint request
            try:
                result = eval(endpoint)
            except Exception, e:
                if len(e.message) == 0:
                    msg = e.__str__()
                else:
                    msg = e.message
                raise RuntimeError("The executed command was: {}\nMessage: {}"\
                                .format(endpoint.replace("\.execute()", ""), msg))
            print "Done in {}ms".format(int(round((time.time() - exec_time) * 1000)))

            if eval_expr:
                if isinstance(eval_expr, str) or isinstance(eval_expr, unicode):
                    exec(eval_expr)
                elif isinstance(eval_expr, list):
                    for expr in eval_expr:
                        exec(expr)

            if print_result == True:
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
                        val = self.__parse_expression(match.group(1), container = result)
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
                            val = self.__parse_expression(match.group(1), container = result)
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

            if result_name:
                if repeat > 1:
                    if not self.output_results.has_key(result_name):
                        self.output_results[result_name] = []

                    self.output_results[result_name].append(result)
                else:
                    self.output_results[result_name] = result

            if export_result:
                with open("{}{}".format(export_result, i), 'w') as f:
                    json.dump(result, f, indent=4, separators=(',', ': '))

            if json_pattern:
                # replace the expressions in the json pattern
                dump = json.dumps(json_pattern)
                did_match = match = self.expression_matcher.search(dump)
                while match:
                    dump = self.expression_matcher.sub(self.__parse_expression(match.group(1)), dump)
                    match = self.expression_matcher.search(dump)

                if did_match:
                    json_pattern = json.loads(dump)

                try :
                    check_json(result, json_pattern)
                except AssertionError, e:
                    print "Assertion failed : "
                    print e.message

    def __parse_expression(self, expression, container = None):
        """
        Parses the jsonpath expression in {self.output_results} and return its result
        """
        if container == None:
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

        if results == False or len(results) == 0:
            raise RuntimeError("The expression {} gave no result".format(expression))

        if as_list:
            return results
        else:
            return results[0]
