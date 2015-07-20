from __future__ import print_function
import json, re, os

class fmt:
    """
    Formating strings
    """
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# set the default colors
error_color = fmt.RED
error_color_detail = fmt.PURPLE
info_color = fmt.BLUE
success_color = fmt.GREEN
end_color = fmt.END
yellow = fmt.YELLOW
bold = fmt.BOLD

# get the number of columns in the terminal
try:
    tty_rows, tty_columns = [int(e) for e in os.popen('stty size', 'r').read().split()]
except:
    # sorry, that works only on Linux and Mac, no windows
    tty_rows = tty_columns = 40

def pretty_json(input, no_print = False):
    """
    JSON pretty printing
    """
    if no_print:
        return json.dumps(input, indent=4, separators=(',', ': '))

    print(json.dumps(input, indent=4, separators=(',', ': ')))

def get_test_file(test_name, test_file):
    """
    Returns the JSON of a test file
    """
    # todo replace relative
    with open("test_files/" + test_name + "_test/" + test_file + ".json", 'r') as f:
        return json.loads(f.read())

    return None

def light_assert(exp, message, exit_on_error=False):
    """
    Does an assert and continues, returns True if it succeded, False otherwise
    """
    try:
        assert exp, message
        return True
    except AssertionError, e:
        print(error_color)
        print("*"*tty_columns)
        print("* FAIL : ", e.message)
        print("*"*tty_columns)
        print(fmt.END)
        if exit_on_error:
            raise AssertionError(e.message)
        else:
            return False


def check_json(result, expectation, path="$", exit_on_error=False, skip_errors=False):
    no_error = True
    orig_path = path

    if isinstance(expectation, unicode) or isinstance(expectation, str):
        expectation = {'':expectation}

    if isinstance(result, unicode) or isinstance(result, str):
        result = {'':result}

    for key in expectation:
        path = orig_path + "." + key
        no_error = True

        # if we expect not having this path
        if expectation[key] == 'nil':
            if not light_assert(not result.has_key(key),
                                "The result should not have the path : {}".format(path),
                                exit_on_error=exit_on_error):
                no_error = False

            # continue in both cases as this key does not exist anyway
            continue

        # otherwise ensures that the result has the same path
        elif not light_assert(result.has_key(key),
                              "The result does not have the path : {}".format(path),
                              exit_on_error=exit_on_error):
            no_error = False
            continue

        exp = expectation[key]
        res = result[key]

        if isinstance(exp, dict):
            check_json(res, exp, path, exit_on_error=exit_on_error)

        elif isinstance(exp, list):
            pattern = ""
            if len(exp) > 0 :
                no_error = light_assert(
                    re.match('#.*#', str(exp[0])),
                    "The first element in the expectation list has to be a pattern enclosed in #, you gave {}".format(exp[0]),
                    exit_on_error=exit_on_error)
                pattern = str(exp[0])

                if len(exp) > 1:
                    exp = exp[1:]

            if len(exp) == 0:
                no_error = light_assert(
                    len(res) == 0,
                    'The number of results in path "{}" is not empty as expected (there were {} entries)'.format(path, len(exp)),
                    exit_on_error=exit_on_error)

            # Check that we have the same number of entries
            elif len(exp) == 1 and re.match('#=[0-9]+#', pattern):
                no_error = light_assert(
                    len(res) == int(re.findall('#=([0-9]+)#', exp[0])[0]),
                    'The number of results in path "{}" does not match what expected (there were {} entries rather than {})'.format(path, len(res), int(re.findall('#=([0-9]+)', exp[0])[0])),
                    exit_on_error=exit_on_error)

            # Check that we have at least one entry
            elif len(exp) == 1 and pattern == "#+#":
                no_error = light_assert(
                    len(res) > 0,
                    'The number of results in path "{}" is empty'.format(path, len(res), len(exp)),
                    exit_on_error=exit_on_error)

            # If any number, do nothing
            elif len(exp) == 1 and pattern == "#*#":
                pass

            # Check all entries respect the pattern
            elif len(exp) == 1 and pattern == "#PATTERN#":
                no_error = light_assert(
                    len(res) > 0,
                    'The number of results in path "{}" is empty'.format(path, len(res), len(exp)),
                    exit_on_error=exit_on_error)

                for index, entry in enumerate(res):
                    check_json(entry, exp[-1], path + "[{}]".format(index + 1), exit_on_error=exit_on_error)

            # Check all entries match exactly the expectations
            elif len(exp) > 0 and pattern == "#ALL#":
                no_error = light_assert(
                    len(res) == len(exp),
                    'The number of results in path "{}" does not match what expected (there were {} entries rather than {})'.format(path, len(res), len(exp)),
                    exit_on_error=exit_on_error)

                iterations = 0
                entries = range(len(res))
                while iterations < len(res):
                    for idx in entries:
                        no_err = check_json(res[idx], exp[idx], path + "[{}]".format(idx + 1), exit_on_error=exit_on_error,
                                skip_errors=True)
                        if no_err:
                            entries.remove(idx)
                            break
                    iterations += 1

                no_error = light_assert(
                    iterations == len(res) and len(entries) == 0,
                    'The results in path "{}" do not match what expected'.format(path),
                    exit_on_error=exit_on_error)
        else:
            exp = str(exp)
            res = str(res)

            # if we are requesting a regexp
            if exp.startswith("#r#"):
                exp = exp.split('#r#')[-1]
                reg = re.compile(exp)
                no_error = light_assert(
                    reg.match(res),
                    ('The result "{}" does not match the regex "{}"'
                     '\n* PATH : {}').format(res, exp, path),
                    exit_on_error=exit_on_error)
            elif not skip_errors:
                no_error = light_assert(
                    res == exp,
                    ('The result "{}" does not match "{}"'
                     '\n* PATH : {}').format(res, exp, path),
                    exit_on_error=exit_on_error)
            elif skip_errors and res == exp:
                no_error = True
            else:
                no_error = False

        if not skip_errors:
            if no_error:
                print(info_color, path, success_color, bold, "DONE", end_color)
            else:
                print(info_color, path, error_color, bold, "FAILURE", end_color)
        else:
            return no_error
