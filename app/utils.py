from __future__ import print_function
import json, re, os

class fmt:
    """
    Formating strings
    """
    PURPLE = '\033[35m'
    CYAN = '\033[36m'
    BLUE = '\033[34m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# set the default colors
error_color = fmt.RED
error_color_detail = fmt.PURPLE
info_color = fmt.BLUE
success_color = fmt.GREEN
warning_color = fmt.YELLOW
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
        if exit_on_error:
            print(error_color)
            print("*"*tty_columns)
            print("* FAIL : ", e.message)
            print("*"*tty_columns)
            print(fmt.END)
            raise AssertionError(e.message)
        else:
            print(warning_color)
            print("*" * tty_columns)
            print("* WARNING : ", e.message)
            print("*" * tty_columns)
            print(fmt.END)
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
                                u"The result should not have the path : {}".format(path),
                                exit_on_error=exit_on_error):
                no_error = False

            # continue in both cases as this key does not exist anyway
            continue

        # otherwise ensures that the result has the same path
        elif not light_assert(result and result.has_key(key),
                              u"The result does not have the path : {}".format(path),
                              exit_on_error=exit_on_error):
            no_error = False
            continue

        exp = expectation[key]
        res = result[key]

        if isinstance(exp, dict):
            no_err = check_json(res, exp, path, exit_on_error=exit_on_error, skip_errors=skip_errors)
            if not no_err and not exit_on_error and skip_errors:
                no_error = False

        elif isinstance(exp, list):
            pattern = ""
            if len(exp) > 0 :
                no_error = light_assert(
                    re.match('#.*#', unicode(exp[0])),
                    u"The first element in the expectation list has to be a pattern enclosed in #, you gave {}".format(exp[0]),
                    exit_on_error=exit_on_error)
                pattern = unicode(exp[0])

                if len(exp) > 1:
                    exp = exp[1:]

            if len(exp) == 0:
                no_error = light_assert(
                    len(res) == 0,
                    u'The number of results in path "{}" is not empty as expected (there were {} entries)'.format(path, len(exp)),
                    exit_on_error=exit_on_error)

            # Check that we have the same number of entries
            elif len(exp) == 1 and re.match('#=[0-9]+#', pattern):
                no_error = light_assert(
                    len(res) == int(re.findall('#=([0-9]+)#', exp[0])[0]),
                    u'The number of results in path "{}" does not match what expected (there were {} entries rather than {})'.format(path, len(res), int(re.findall('#=([0-9]+)', exp[0])[0])),
                    exit_on_error=exit_on_error)

            elif len(exp) == 1 and re.match('#>=[0-9]+#', pattern):
                no_error = light_assert(
                    len(res) >= int(re.findall('#>=([0-9]+)#', exp[0])[0]),
                    u'The number of results in path "{}" does not match what expected (there were {} entries rather than at least {})'.format(path, len(res), int(re.findall('#>=([0-9]+)', exp[0])[0])),
                    exit_on_error=exit_on_error)

            elif len(exp) == 1 and re.match('#<=[0-9]+#', pattern):
                no_error = light_assert(
                    len(res) <= int(re.findall('#<=([0-9]+)#', exp[0])[0]),
                    u'The number of results in path "{}" does not match what expected (there were {} entries rather than {} maximum)'.format(path, len(res), int(re.findall('#<=([0-9]+)', exp[0])[0])),
                    exit_on_error=exit_on_error)

            elif len(exp) == 1 and re.match('#>[0-9]+#', pattern):
                no_error = light_assert(
                    len(res) > int(re.findall('#>([0-9]+)#', exp[0])[0]),
                    u'The number of results in path "{}" does not match what expected (there were {} entries rather than more than {})'.format(path, len(res), int(re.findall('#>([0-9]+)', exp[0])[0])),
                    exit_on_error=exit_on_error)

            elif len(exp) == 1 and re.match('#<[0-9]+#', pattern):
                no_error = light_assert(
                    len(res) < int(re.findall('#<([0-9]+)#', exp[0])[0]),
                    u'The number of results in path "{}" does not match what expected (there were {} entries rather than less than {})'.format(path, len(res), int(re.findall('#<([0-9]+)', exp[0])[0])),
                    exit_on_error=exit_on_error)

            # Check that we have at least one entry
            elif len(exp) == 1 and pattern == "#+#":
                no_error = light_assert(
                    len(res) > 0,
                    u'The number of results in path "{}" is empty'.format(path, len(res), len(exp)),
                    exit_on_error=exit_on_error)

            # If any number, do nothing
            elif len(exp) == 1 and pattern == "#*#":
                pass

            # Check all entries respect the pattern
            elif len(exp) == 1 and pattern == "#PATTERN#":
                no_error = light_assert(
                    len(res) > 0,
                    u'The number of results in path "{}" is empty'.format(path, len(res), len(exp)),
                    exit_on_error=exit_on_error)

                for index, entry in enumerate(res):
                    check_json(entry, exp[-1], path + "[{}]".format(index + 1), exit_on_error=exit_on_error)

            # Check all entries match exactly the expectations
            elif len(exp) > 0 and pattern == "#ALL#":
                no_error = light_assert(
                    len(res) == len(exp),
                    u'The number of results in path "{}" does not match what expected (there were {} entries rather than {})'.format(path, len(res), len(exp)),
                    exit_on_error=exit_on_error)

                iterations = 0
                entries = range(len(res))
                exp_cpy = exp[:]
                while iterations < len(res):
                    exp_val = exp_cpy.pop()
                    for idx in entries:
                        no_err = check_json(res[idx], exp_val, path + "[{}]".format(idx + 1), exit_on_error=exit_on_error,
                                skip_errors=True)
                        if no_err:
                            entries.remove(idx)
                            break
                    iterations += 1

                no_error = light_assert(
                    iterations == len(res) and len(entries) == 0,
                    'The results in path "{}" do not match what expected'.format(path),
                    exit_on_error=exit_on_error)

            # Check that at least one entry match the expectation
            elif len(exp) > 0 and pattern == "#ANY#":
                no_error = light_assert(
                    len(exp) == 1,
                    u'The number of items in #ANY# command must be exactly 2 (there was {})'.format(len(exp)),
                    exit_on_error=exit_on_error)

                no_error = light_assert(
                    any([r == exp[0] for r in res]),
                    'The results in path "{}" do not match what expected'.format(path),
                    exit_on_error=exit_on_error)

            # Check all entries are matching elements.
            # It's a mix of PATTERN and ALL.
            # Number of items must match number of expected results, and expected results must respect pattern.
            elif len(exp) > 0 and pattern == "#MATCH#":
                light_assert(
                    len(res) == len(exp),
                    u'The number of results in path "{}" does not match what expected (there were {} entries rather than {})'.format(path, len(res), len(exp)),
                    exit_on_error=exit_on_error)

                iterations = 0
                entries = range(len(res))
                while iterations < len(res):
                    for idx in entries:
                        no_err = check_json(res[iterations], exp[idx], path + "[{}]".format(idx + 1), exit_on_error=False,
                                            skip_errors=True)
                        if no_err:
                            entries.remove(idx)
                            break
                    iterations += 1

                no_error = light_assert(
                    iterations == len(res) and len(entries) == 0,
                    'The results in path "{}" do not match what expected'.format(path),
                    exit_on_error=exit_on_error)

            # It's a mix of MATCH and ANY.
            # Check at least one item is respecting pattern. No check on number of items matching.
            elif len(exp) > 0 and pattern == "#MATCH_ANY#":
                light_assert(
                    len(res) > 0,
                    u'No result in path "{}", at least one is expected'.format(path),
                    exit_on_error=exit_on_error)

                nb_matching = 0
                entries = xrange(len(res))
                for iterations in xrange(len(exp)):
                    for idx in entries:
                        no_err = check_json(res[idx], exp[iterations], path + "[{}]".format(idx + 1), exit_on_error=False,
                                            skip_errors=True)
                        if no_err:
                            nb_matching += 1
                            break

                no_error = light_assert(
                    len(exp) == nb_matching,
                    'The results in path "{}" do not match what expected'.format(path),
                    exit_on_error=exit_on_error)

            # Negative case of ALL
            # check that no item match unexpected expression
            elif len(exp) > 0 and pattern == "#NOT_ALL#":
                for ex in exp:
                    no_error = light_assert(
                        not any([r == ex for r in res]),
                        'The results in path "{}" match unexpected item'.format(path),
                        exit_on_error=exit_on_error)

            # Negative case of MATCH
            # check that no item match unexpected pattern. No check on number of items matching.
            elif len(exp) > 0 and pattern == "#NOT_MATCH#":
                for iterations, _ in enumerate(res):
                    for idx, _ in enumerate(exp):
                        no_err = check_json(res[iterations], exp[idx], path + "[{}]".format(idx + 1),
                                            exit_on_error=False,
                                            skip_errors=True)

                        no_error = light_assert(
                            not no_err,
                            'The results in path "{}[{}]" match unexpected pattern {}'.format(path, iterations + 1, exp[idx]),
                            exit_on_error=exit_on_error)

        else:
            exp = unicode(exp)
            res = unicode(res)

            # if we are requesting a regexp
            if exp.startswith("#r#"):
                exp = exp.split('#r#')[-1]
                reg = re.compile(exp)
                no_error = light_assert(
                    reg.match(res),
                    (u'The result "{}" does not match the regex "{}"'
                     u'\n* PATH : {}').format(res, exp, path),
                    exit_on_error=exit_on_error)
            elif not skip_errors:
                no_error = light_assert(
                    res == exp,
                    (u'The result "{}" does not match "{}"'
                     u'\n* PATH : {}').format(res, exp, path),
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
        elif no_error is False:
            # break loop only if a test fail, else continue to check other items of `expectation`.
            return False

    if skip_errors:
        return no_error


def check_order_values(results, directions, paths=None, exit_on_error=False, skip_errors=False):
    """
    Check if values are correctly sorted.
    If there are multiple sort order criteria, check the first, and if there is an equality, check the next criteria
    """
    no_error = True

    if no_error and len(results) > 0:
        previous = None
        result = results[0]
        direction = directions[0]
        path = paths[0] or "$"

        no_error = light_assert(
            direction in ['asc', 'desc'],
            u'The sort direction "{}" is incorrect. Must be "{}" or "{}"'.format(direction, 'asc', 'desc'),
            exit_on_error
        )

        for index, val in enumerate(result):
            if not previous:
                previous = val
            elif previous == val:
                # if value is identical to previous, check if there is another criteria in the list
                no_error &= check_order_values(results[1:], directions[1:], paths[1:], exit_on_error, skip_errors)
            else:
                comparator = "<=" if direction == 'asc' else ">="
                no_error &= light_assert(
                    previous <= val if direction == 'asc' else previous >= val,
                    u'The result "{}" is not sorted as expected. {} {} {} is false'.format(path, previous, comparator,
                                                                                           val),
                    exit_on_error
                )
                previous = val


        if not skip_errors:
            if no_error:
                print(info_color, path, success_color, bold, "DONE", end_color)
            else:
                print(info_color, path, error_color, bold, "FAILURE", end_color)
        # else:
    return no_error

