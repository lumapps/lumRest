# Endpoint Tester#
Allows the user to write test scenarios for Google Cloud Endpoints using a combination of `yaml` and `json` files.
# Usage #
The basic usage can be found by running the script with a `-h` option.
```bash
./lumrest.py -h
usage: lumrest.py [-h] [--parser PARSER] [--auth AUTH_CONFIG_FILE] SCENARIO_FILE

Endpoint tester

positional arguments:
  SCENARIO_FILE         The path to the scenario file

optional arguments:
  -h, --help               show this help message and exit
  --parser PARSER          A python file that is used to parse the scenario commands
  --auth AUTH_CONFIG_FILE  The configuration file containg authentication information
```

The script has one mandatory argument (the scenario file) and two optional (authentication config file and a command parser). In the following, we will use the [urlshortener API](https://developers.google.com/url-shortener/) from Google.

## Scenarios ##
The scenario file has to be in `yaml` format. The possible keys are:
- `name`: the name of the scenario.
- `service`: describes the service on which you'd like to run the test (see [Service](#service))
- `commands`: the list of commands to be executed (see [Commands](#commands))

### Service ###
Three keys are required `api`, `version` and the `discovery_url`. For the urlshortener example we have:
```yaml
service:
    api: "urlshortener"
    version: "v1"
    discovery_url: "https://www.googleapis.com/discovery/v1/apis/urlshortener/v1/rest"
```
### Commands ###
The commands are defined in a list form. Each list entry has a mandatory key being the endpoint to be called and some optional keys:
- `save_result`: saves the result of this endpoint. Its value is the name used to reference it (see [Save](#save))
- `export_result`: saves the result to a file, its value is the file name.
- `print_result`: outputs the result of this endpoint execution to stdout  (see [Print](#print))
- `check_result`: checks that the result respect the given pattern. If a json file is given, reads it and uses it to check  (see [Check](#check))

Suppose we have the following urlshortener example:
```yaml
commands:
  - url.insert:
      body: { "longUrl" : "http://google.com" }
    print_result: !expr id
    save_result: compressed
  - url.get:
      shortUrl: !expr compressed.id
    print_result: true
    check_result: {"longUrl" : "#r#http://google.com/?" }
```
The first command calls the endpoint `url.insert` with the argument `body`. When the `body` value is a python dictionary, its value is parsed as Json. Otherwise, it is considered as a Json file name and its content is used in the request.
Next, we'd like to print the result of the command, when the `print_result` value is a string preceded by `!expr`, its value is parsed as a JsonPath expression. Finaly, we save the result as `compressed` for later use.

The second command calls the endpoint `url.get` with the argument `shortUrl`. When an argument, other than `body`, is a string preceded by `!expr`, its value is evaluated as a JsonPath expression and applied on the saved results. Here, we try to reference the `id` from `compressed`, the result of the previous command.
Next, we print the result, if the command `print_result` is true, we print the whole Json response. Then we call `check_result` with an expression being a Json object. The value of `longUrl` is preceded by `#r#` to say that the value is a regular expression, which checks if the url ends with a `/` or not. For more details on these commands see [Check](#check).

#### Save ####
The option `save_result` takes as argument the name of the result that can be used later. The results are stored in a dictionary. Therefore, any reuse of that name in the `save_result` option will overwrite its previous value.
#### Print ####
The option `print_result` takes either a boolean or a jsonpath expression. If the former is given, the script will print the whole json response. If the latter is given, it has to be preceded by a `!expr` keyword and whatever comes after it is interpreted using the [jsonpath](https://pypi.python.org/pypi/jsonpath/) library.
If this option is given as a list, for example
```yaml
print_result:
    - !expr id
    - !expr status
```
the script prints the commands successively.
#### Check ####
The option `check_result` behaves exactly as the `body` argument of the commands. The json content is parsed and the script checks that every entry in the `check_result` json content is in the response. If some data is in the response and not in the json content, no error is raised.

The `check_result` json content has some additional parameters that can be used to validate that the received response is correct:

- In the case of primitive values (String, Boolean, etc)
    * Check that `"value"` is exactly what was received
    ```json
    "key" : "value"
    ```
    * Check that `"value"` maches (regexp) what was received
    ```json
    "key" : "#r#value"
    ```

- For Lists, we can check almost anything
    * Empty list means that the result has to be empty
    ```json
    "key" : []
    ```
    * Lists starting with `"#=<scalar>#"` check that there are as many results as expected objects. This example:
    ```json
    "key" : [ "#=2#" ]
    ```
    checks that there are two and only two objects in the list without checking their content.
    * Lists starting with `"#+#"` check that there is at least one object.
    ```json
    "key" : [ "#+#" ]
    ```
    * Lists starting with `"#*#"` check that the list can contain any number of elements, including empty ones.
    ```json
    "key" : [ "#*#" ]
    ```
    * Lists starting with `"#PATTERN#"` check that all the entries of the list respect the pattern of the object that follows.
    ```json
    "key" : [ "#PATTERN#", { "key2" : "value", "key3" : "#r#val" }]
    ```
    * Lists starting with `"#ALL#"` check that all the entries of the list respect exactly the pattern of each corresponding object in the list. For instance, the template:
    ```json
    "key" : [ "#ALL#", obj1, obj2]
    ```
    checks that the result has exactly two entries, the first one respect the template of obj1 and the second respects the template of obj2

## Authentication ##
To use services that require authentication, you have to call the script with `--auth=config.yaml` where `config.yaml` is a file containing the key `auth` as in:
```yaml
auth:
  email: "someone@somewhere.net"
  client_secret: "/path/to/secrete/key.pem"
  client_id: "my-client-id@dev.service-account.com"
  oauth_scope:
      - "https://www.googleapis.com/auth/userinfo.email"
```

See [Getting Started with Google Tasks API on Google App Engine](https://cloud.google.com/appengine/articles/python/getting_started_with_tasks_api) for more details.


# Examples #
## Url shortener ##
Running the scenario:
```yaml
#name of the test
name: Test Shortened urls

# service information
service:
    api: "urlshortener"
    version: "v1"
    discovery_url: "https://www.googleapis.com/discovery/v1/apis/urlshortener/v1/rest"

# this section is not used by the script, but can be helpful for the commands
websites : &w01 "http://google.com"
websites : &w02 "http://google.com/"

# the commands
commands:
  - url.insert:
      body: {"longUrl" : *w01}
    print_result: !expr id
    save_result: compressed_1
    check_result: {
                    # the urlshortener service adds a '/' at the end
                    "longUrl" : *w02
                  }

  - url.insert:
      body: {"longUrl" : *w02}
    print_result: true
    save_result: compressed_2
    check_result: {
                    # this should have the same id as the previous one
                    "id" : !expr compressed_1.id,
                    "longUrl" : *w02
                  }

  - url.insert:
      body: {"longUrl" : *w02}
    print_result: true
    save_result: compressed_2
    check_result: {
                    # make it fail!
                    "longUrl" : "aaa"
                  }

  - url.get:
      shortUrl: !expr compressed_1.id
    print_result: true
    check_result: {
                    "longUrl" : "#r#http[s]?://google.com/?"
                  }
```
Gives:
```text
Running scenario Test Shortened urls

Executing : url.insert
Done in 40ms

Content of id:
"http://goo.gl/mR2d"

 $.longUrl   DONE

Executing : url.insert
Done in 32ms

Result JSON:
{
    "kind": "urlshortener#url",
    "id": "http://goo.gl/mR2d",
    "longUrl": "http://google.com/"
}

 $.longUrl.id   DONE

Executing : url.insert
Done in 33ms

Result JSON:
{
    "kind": "urlshortener#url",
    "id": "http://goo.gl/mR2d",
    "longUrl": "http://google.com/"
}


**********************************************************************************************************
* FAIL :  The result "http://google.com/" does not match "aaa"
* PATH : $.longUrl
**********************************************************************************************************

 $.longUrl   FAILURE

Executing : url.get
Done in 35ms

Result JSON:
{
    "status": "OK",
    "kind": "urlshortener#url",
    "id": "http://goo.gl/mR2d",
    "longUrl": "http://google.com/"
}

 $.longUrl   DONE
```
