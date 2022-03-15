## Cloud VPS API Setup
See [this README](https://github.com/wikimedia/research-api-endpoint-template/blob/master/README.md) for in-depth details on setup, configuration, and debugging.

## LanguageTools
* Based on these instructions: https://dev.languagetool.org/http-server
* Supports these endpoints (all prefixed with `v2`): https://languagetool.org/http-api/swagger-ui/#!/default/post_check

### Things to check
* Depends on Java8 as downloaded/installed via `cloudvps_setup.sh`
* If the LanguageTool package is updated, this could break updates and the path in `model.service` would need to be updated
* Additional configuration can be added via `model.service` as seen below:

```
Usage: HTTPServer [--config propertyFile] [--port|-p port] [--public]
  --config FILE  a Java property file (one key=value entry per line) with values for:
                 'maxTextLength' - maximum text length, longer texts will cause an error (optional)
                 'maxTextHardLength' - maximum text length, applies even to users with a special secret 'token' parameter (optional)
                 'secretTokenKey' - secret JWT token key, if set by user and valid, maxTextLength can be increased by the user (optional)
                 'maxCheckTimeMillis' - maximum time in milliseconds allowed per check (optional)
                 'maxErrorsPerWordRate' - checking will stop with error if there are more rules matches per word (optional)
                 'maxSpellingSuggestions' - only this many spelling errors will have suggestions for performance reasons (optional,
                                            affects Hunspell-based languages only)
                 'maxCheckThreads' - maximum number of threads working in parallel (optional)
                 'cacheSize' - size of internal cache in number of sentences (optional, default: 0)
                 'cacheTTLSeconds' - how many seconds sentences are kept in cache (optional, default: 300 if 'cacheSize' is set)
                 'requestLimit' - maximum number of requests per requestLimitPeriodInSeconds (optional)
                 'requestLimitInBytes' - maximum aggregated size of requests per requestLimitPeriodInSeconds (optional)
                 'timeoutRequestLimit' - maximum number of timeout request (optional)
                 'requestLimitPeriodInSeconds' - time period to which requestLimit and timeoutRequestLimit applies (optional)
                 'languageModel' - a directory with '1grams', '2grams', '3grams' sub directories which contain a Lucene index
                                   each with ngram occurrence counts; activates the confusion rule if supported (optional)
                 'word2vecModel' - a directory with word2vec data (optional), see
                  https://github.com/languagetool-org/languagetool/blob/master/languagetool-standalone/CHANGES.md#word2vec
                 'fasttextModel' - a model file for better language detection (optional), see
                                   https://fasttext.cc/docs/en/language-identification.html
                 'fasttextBinary' - compiled fasttext executable for language detection (optional), see
                                    https://fasttext.cc/docs/en/support.html
                 'maxWorkQueueSize' - reject request if request queue gets larger than this (optional)
                 'rulesFile' - a file containing rules configuration, such as .langugagetool.cfg (optional)
                 'warmUp' - set to 'true' to warm up server at start, i.e. run a short check with all languages (optional)
                 'blockedReferrers' - a comma-separated list of HTTP referrers (and 'Origin' headers) that are blocked and will not be served (optional)
                 'premiumOnly' - activate only the premium rules (optional)
                 'disabledRuleIds' - a comma-separated list of rule ids that are turned off for this server (optional)
                 'pipelineCaching' - set to 'true' to enable caching of internal pipelines to improve performance
                 'maxPipelinePoolSize' - cache size if 'pipelineCaching' is set
                 'pipelineExpireTimeInSeconds' - time after which pipeline cache items expire
                 'pipelinePrewarming' - set to 'true' to fill pipeline cache on start (can slow down start a lot)
                 Spellcheck-only languages: You can add simple spellcheck-only support for languages that LT doesn't
                                            support by defining two optional properties:
                   'lang-xx' - set name of the language, use language code instead of 'xx', e.g. lang-tr=Turkish
                   'lang-xx-dictPath' - absolute path to the hunspell .dic file, use language code instead of 'xx', e.g.
                                        lang-tr-dictPath=/path/to/tr.dic. Note that the same directory also needs to
                                        contain a common_words.txt file with the most common 10,000 words (used for better language detection)
  --port, -p PRT   port to bind to, defaults to 8081 if not specified
  --public         allow this server process to be connected from anywhere; if not set,
                   it can only be connected from the computer it was started on
  --allow-origin [ORIGIN] set the Access-Control-Allow-Origin header in the HTTP response,
                         used for direct (non-proxy) JavaScript-based access from browsers.
                         Example: --allow-origin "https://my-website.org"
                         Don't set a parameter for `*`, i.e. access from all websites.
  --verbose, -v    in case of exceptions, log the input text (up to 500 characters)
  --languageModel  a directory with '1grams', '2grams', '3grams' sub directories (per language)
                         which contain a Lucene index (optional, overwrites 'languageModel'
                         parameter in properties files)
  --word2vecModel  a directory with word2vec data (optional), see
                   https://github.com/languagetool-org/languagetool/blob/master/languagetool-standalone/CHANGES.md#word2vec
  --premiumAlways  activate the premium rules even when user has no username/password - useful for API servers
```