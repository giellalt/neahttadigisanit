"""Morphological tools"""

import heapq

# anders: note for the future:
# the "imp" module was deprecated in python v3.4, and removed since v3.12
# superseeded by importlib
import imp
import os
import re
import sys
from termcolor import colored

try:
    import hfst
    from hfst.exceptions import NotTransducerStreamException

    HAVE_PYHFST = True
except ImportError:
    HAVE_PYHFST = False

from neahtta.utils.remove_duplicates import remove_duplicates
from neahtta.utils.partition import partition_in_place, partition_in_place_stable


# TODO: get from global path
configs_path = os.path.join(os.path.dirname(__file__), "../")


class TagPart:
    """This is a part of a tag, which should behave mostly like a string:

        >>> v = TagPart('V')
        >>> v == 'V'
        True

    Except when some additional attributes are defined to allow for
    regular expression matching

        >>> v = TagPart({'match': '^PV', 'regex': True})
        >>> v == 'bbq'
        False
        >>> v == 'PV/e'
        True
    """

    def __init__(self, t):
        self.t = t
        if not isinstance(t, dict):
            self.val = t
            self.regex = None
        else:
            self.val = t.get("match")
            self.regex = t.get("regex")
            if self.regex:
                self._re = re.compile(self.val)

    def __repr__(self):
        return self.val

    def __hash__(self) -> int:
        return hash(self.t)

    def __eq__(self, other) -> bool:
        if not self.regex:
            return self.val == other
        else:
            return self._re.match(other) is not None


class Tagset:
    def __init__(self, name, members):
        self.name = name
        self.members = list(map(TagPart, members))

    def __str__(self) -> str:
        return f'<Tagset: "{self.name}">'

    def __contains__(self, item) -> bool:
        return item in self.members


class Tagsets:
    """Represents the dictionary of tagsets read from a yaml .tagset file
    found in src/configs/language_specific_rules/tagsets.
    These files contains mapping of names to string entries, such as:
    "pos" = ["A", "Adp", "N", ...]
    "pron_type" = ["Dem", "Indef", "Interr", "Pers", ...]

    This class has an underlying dictionary of those keys ("pos", "pron_type",
    ...), with values that are themselves the list of tags, wrapped in a
    Tagset.
    """

    def __init__(self, set_definitions):
        self.sets = {name: Tagset(name, tags) for name, tags in set_definitions.items()}

    def __getitem__(self, key) -> Tagset:
        return self.sets[key]

    def __contains__(self, key) -> bool:
        return key in self.sets

    def all_tags(self) -> list[str]:
        """All unique tags found over all sets. For example, the tag "Indef"
        is listed under both the "pron_type" set, and the "type" set.
        """
        # TODO the return value is used for member checking, so make it
        # a set instead of a list
        tags = set()
        for tagset in self.sets.values():
            for tag in tagset.members:
                tags.add(tag)

        new_result = list(tags)

        # old code
        list_of_lists = [list(v.members) for k, v in self.sets.items()]
        flattened_list = list(item for sublist in list_of_lists for item in sublist)
        _all = list(set(flattened_list))

        assert new_result == _all, "old and new code does the same"
        return _all


class Tag:
    """A model for tags. Can be used as an iterator, as well.

    #>> for part in Tag('N+G3+Sg+Ill', '+'):
    #>>     print part

    Also, indexing is the same as Tag.getTagByTagset()

    >>> _type = Tagset('type', ['G3', 'NomAg'])
    >>> _case = Tagset('case', ['Nom', 'Ill', 'Loc'])
    >>> _ng3illsg = Tag('N+G3+Sg+Ill', '+')
    >>> _ng3illsg[_type]
    'G3'
    >>> _ng3illsg[_case]
    'Ill'
    >>> _pv = Tagset('preverb', ['1', '2', {'match': '^PV', 'regex': True}])
    >>> pv_tag = Tag('PV/e+V+Sg', '+')
    >>> 'PV/e' in _pv
    True
    >>> pv_tag[_pv]
    'PV/e'
    >>> pv_tag = Tag('PV/omgbbq+V+Sg', '+')
    >>> 'PV/omgbbq' in _pv
    True
    >>> pv_tag[_pv] != 'PV/e'
    True

    TODO: maybe also contains for tag parts and tagsets

    TODO: begin integrating Tag and Tagsets into morphology code below,
    will help when generalizing the lexicon-morphology 'type' and 'pos'
    stuff. E.g., in `sme`, we look up words by 'pos' and 'type' when it
    exists, but in other languages this will be different. As such, we
    will need `Tag`, and `Tagset` and `Tagsets` to mitigate this.

    Also, will need some sort of lexicon lookup definition in configs,
    to describe how to bring these items together.
    """

    def __init__(self, string: str, sep: str, tagsets=None):
        self.tag_string = string
        self.sep = sep
        self.parts = self.tag_string.split(sep)
        if tagsets is None:
            self.sets = {}
        elif isinstance(tagsets, Tagsets):
            self.sets = tagsets.sets
        elif isinstance(tagsets, dict):
            self.sets = tagsets
        else:
            self.sets = tagsets

    def __contains__(self, b):
        if isinstance(b, str):
            return self.sets.get(b, False)
        return False

    def __getitem__(self, b):
        """Overloading the xor operator to produce the tag piece that
        belongs to a given tagset."""
        _input = b
        if isinstance(b, int):
            return self.parts[b]
        if isinstance(b, str):
            b = self.sets.get(b, False)
            if not b:
                _s = ", ".join(self.sets.keys())
                raise IndexError(f"Invalid tagset <{_input}>. Choose one of: {_s}")
        elif isinstance(b, Tagset):
            pass
        return self.getTagByTagset(b)

    def __iter__(self):
        for x in self.parts:
            yield x

    def __str__(self):
        return f"<Tag: {self.sep.join(self.parts)}>"

    def __repr__(self):
        return f"<Tag: {self.sep.join(self.parts)}>"

    def matching_tagsets(self):
        ms = {}
        for key in self.sets:
            if self[key]:
                ms[key] = self[key]
        return ms

    def getTagByTagset(self, tagset):
        for p in self.parts:
            if p in tagset.members:
                return p

    def splitByTagset(self, tagset):
        """
        #>> tagset = Tagset('compound', ['Cmp#'])
        [Cmp#]
        #>> tag = Tag('N+Cmp#+N+Sg+Nom')
        #>> tag.splitByTagset(tagset)
        [<Tag: N>, <Tag: N+Sg+Nom>]
        """
        raise NotImplementedError


class Lemma:
    """Lemma class that is bound to the morphology"""

    def __init__(self, tag, _input, tool, tagsets):
        self.tool = tool

        self.tag = self.tool.tagStringToTag(tag, tagsets=tagsets)

        actio_with_tagsep = self.tool.options.get(
            "actio_tag", "Actio"
        ) + self.tool.options.get("tagsep", "+")

        # Best guess is the first item, otherwise...
        # TODO the assumptions in this file does not always hold,
        # something is incorrect somewhere
        # anders: I'm getting that this makes the pos the lemma, presumably
        # because it's already been stripped out somewhere before
        # anders: yeah, sometimes this is literaly "N" (for example)
        lemma = tag[0]
        # Best guess is the first item, otherwise...
        # self.lemma = tag[0]
        # del tag[0]
        actio = False
        if actio_with_tagsep in tag:
            # anders:
            # - actio_with_tagsep is essentially always "Actio+" for us
            # - tag is a Tag, which will split by "+",
            # - Tag.__contains__() just does a __contains__ on the underlying
            #   .sets dictionary, which is built by splitting the input string
            #   by "+"
            # hence: A string which includes "+" is never in tag, and this
            # branch is never taken.
            assert False, "unreachable"
            lemma = tag
            self.lemma = lemma
            actio = True
            self.pos = ""
            self.tag_raw = [tag]
        else:
            all_tags = tagsets.all_tags()
            if lemma not in all_tags:
                # anders:
                # the first "part" of the Tag was not a known tag, so we
                # are certain that the first part is the lemma, such as in
                # "konspirasjon+N+Sg+Indef" (example tags probably wrong,
                # but just for demonstrative purposes here)
                self.lemma = lemma
            else:
                # anders:
                # corner-case, the lemma is precisely (case sensitively)
                # exactly a tag, such as e.g. "Ord", "Dem", "Aktor", "Ess", ..
                # So what this code does is somehow try to see if this is
                # the lemma, or the lemma has already been extracted?

                # Separate out items that are not values in a tagset, these
                # are probably the lemma.
                not_tags = [t for t in tag if t not in all_tags]
                if len(not_tags) > 0:
                    # anders: so here, we have found a "tag" in the tag list
                    # that is in fact, not a tag, so the code assumes that
                    # the lemma is the first such entry
                    self.lemma = not_tags[0]
                else:
                    # anders: but here, logically, len(not_tags) == 0,
                    # which means all elements of the tag was found to be
                    # actual tags -- and so it is presumed that the lemma
                    # must therefore be the first tag anyway?
                    self.lemma = tag[0]

        if not actio:
            # anders:
            # the branch above which sets actio to True is unreachable code,
            # so this always happens...
            self.pos = self.tag["pos"]
            self.tag_raw = tag
        else:
            # anders:
            # ...which means that this should be unreachable, too
            # (I added this else branch, and placed unreachable)
            assert False, "unreachable"
        # self.prepare_tag() ends here

        if "pos" in self.tag:
            # anders: I checked, every .tagset file has a member "pos",
            # which is a list of strings. Therefore, this branch is always
            # taken...
            # anders: correction: the assumption that the self.tag is always
            # a full analysis line (like e.g. "beaggit+V+IV+Actio+Gen") is
            # not true. Sometimes, for some reason which I do not understand
            # yet, such a string can be split into "beaggit+V+IV" and then
            # "Actio+Gen" alone. The latter, when it gets run through Tag,
            # does not have a Pos. Or, rather, self.tag always has a Pos,
            # but when looking up the Pos, it may be None, because the "tag"
            # "Actio+Gen" does not have a pos (none of the words, when split
            # by "+" ("Actio", and "Gen") is a valid pos.
            # This can be brittle. If another "Actio variant" is introduced,
            # which collides with any pos, there can be trouble. However,
            # this is probably something which is already a limitation in
            # the tag-format, so it's my understanding that there is awareness
            # of this.
            self.pos = self.tag["pos"]
        else:
            # ... and this never happens (but it's not logically unreachable
            # code)
            assert False, "tagset file always has a 'pos'"
            self.pos = self.tag.parts[0]

        # Letting pos be None is problematic when sorting or grouping by pos
        if self.pos is None:
            # anders: because all tagset files has a pos which is defined
            # as a list, this branch is never taken.
            # anders: correction: (see above) a Tag is not always a
            # representation of a full "tag line" (such as for example
            # "beaggit+V+IV+Actio+Gen"), but sometimes just "Actio+Gen")
            # why? It has something to do with overloading of lemmas in
            # the dictionary, for showing information about tags.
            # In the example I am strugging with ("beaggin"), there is an
            # "Actio+Gen", and that exact entry is not a lemma in the dictioanry,
            # but other "Actio+..." is. Therefore, the original code does not
            # show a dictionary entry for the "Actio+Gen" (that is, the left
            # side of the search result is blank - but, the "Actio+Gen" is shown
            # to the right, as an entry in "other analysis without a translation"-
            # -list.
            # assert False, "self.pos is never None"
            if (
                "verb_derivations" in tagsets
                and self.lemma in tagsets["verb_derivations"]
            ):
                # e.g. VAbess does not have a marked pos
                self.pos = "V"
            elif (
                "adjective_derivations" in tagsets
                and self.lemma in tagsets["adjective_derivations"]
            ):
                self.pos = "A"
            else:
                self.pos = "Unknown"
                error_msg = (
                    f'No part of speech found for lemma "{self.lemma}". '
                    "Make sure it is listed in the appropriate tagset file"
                )
                print(colored(error_msg, "yellow"), flush=True)
        self.input = _input
        self.form = _input

    def __key(self):
        return (self.lemma, self.pos, self.tool.formatTag(self.tag_raw))

    def __eq__(x, y):
        return x.__key() == y.__key()

    def __hash__(self):
        return hash(self.__key())

    def __repr__(self):
        lem, pos, tag = self.__key()
        return f"<{self.__class__.__name__}: {self.form}, {lem}, {pos}, {tag}>"


class GeneratedForm(Lemma):
    """Helper class for generated forms, adds attribute `self.form`,
    alters repr format."""

    def __init__(self, *args, **kwargs):
        super(GeneratedForm, self).__init__(*args, **kwargs)
        self.form = self.input


def word_generation_context(
    generated_result, *generation_input_args, **generation_kwargs
):
    """**Post-generation filter***

    Include context for verbs in the text displayed in paradigm
    generation. The rule in this case is rather complex, and looks at
    the tag used in generation.

    Possible contexts:
      * (mun) dieđán
    """
    language = generation_kwargs.get("language")

    from jinja2 import Template
    from flask import current_app

    context_for_tags = current_app.config.paradigm_contexts.get(language, {})

    node = generation_input_args[2]

    if len(node) == 0:
        return generated_result

    context = node.xpath(".//l/@context")
    context = None if not context else context[0]

    def apply_context(form):
        #        tag, forms = form

        # trigger different tuple lengths and adjust the entities
        # ([u'viessat', u'V', u'Ind', u'Prt', u'Pl1'], [u'viesaimet'])
        # ==>  (u'viessat', [u'V', u'Ind', u'Prt', u'Pl1'], [u'viesaimet'])

        # fix for the bug 2406
        if len(form) == 2:
            tmp_tag, tmp_forms = form
            tmp_lemma = tmp_tag[0]
            tmp_tag = tmp_tag[1 : len(tmp_tag)]
            form = (tmp_lemma, tmp_tag, tmp_forms)

        lemma, tag, forms = form

        tag = "+".join(tag)

        # Get the context, but also fall back to the None option.
        context_formatter = context_for_tags.get(
            (context, tag),
            context_for_tags.get((None, tag), False),
        )

        if context_formatter:
            formatted = []
            if forms:
                for f in forms:
                    _kwargs = {"word_form": f, "context": context}
                    if isinstance(context_formatter, Template):
                        f = context_formatter.render(**_kwargs)
                    else:
                        f = context_formatter % _kwargs
                    formatted.append(f)
            formatted_forms = formatted
        else:
            formatted_forms = forms

        tag = tag.split("+")

        return (tag, formatted_forms)

    return list(map(apply_context, generated_result))


class GenerationOverrides:
    """Class for collecting functions marked with decorators that
    provide special handling of tags. One class instantiated in
    morphology module: `generation_overrides`.

    #>> @generation_overrides.tag_filter_for_iso('sme')
    #>> def someFunction(form, tags, xml_node):
    #>>     ... some processing on tags, may be conditional, etc.
    #>>     return form, tags, xml_node

    Each time morphology.generation is run, the args will be passed
    through all of these functions in the order that they were
    registered, allowing for language-specific conditional rules for
    filtering.

    There is also a post-generation tag rewrite decorator registry function
    """

    ##
    ### Here are the functions that apply all the rules
    ##

    def restrict_tagsets(self, lang_code, function):
        """This runs through each function in the tagset restriction
        registry, and applies it to the input arguments of the decorated
        function.
        """

        def decorate(*args, **kwargs):
            newargs = args
            newkwargs = kwargs
            for f in self.registry[lang_code]:
                newargs = f(*newargs, **newkwargs)
            return function(*newargs, **newkwargs)

        return decorate

    def process_generation_output(self, lang_code, function):
        """This runs the generator function, and applies all of the
        function contexts to the output. Or in other words, this
        decorator works on the output of the decorated function, but
        also captures the input arguments, making them available to each
        function in the registry.
        """

        def decorate(*input_args, **input_kwargs):
            generated_forms, stdout, stderr = function(*input_args, **input_kwargs)
            for f in self.postgeneration_processors[lang_code]:
                generated_forms = f(generated_forms, *input_args, **input_kwargs)
            for f in self.postgeneration_processors["all"]:
                input_kwargs["language"] = lang_code
                if f not in self.postgeneration_processors[lang_code]:
                    generated_forms = f(generated_forms, *input_args, **input_kwargs)
            return generated_forms, stdout, stderr

        return decorate

    def process_analysis_output(self, lang_code, function):
        """This runs the analysis function, and applies all of the
        function contexts to the output. Or in other words, this
        decorator works on the output of the decorated function, but
        also captures the input arguments, making them available to each
        function in the registry.
        """

        def decorate(*input_args, **input_kwargs):
            generated_forms = function(*input_args, **input_kwargs)
            for f in self.postanalyzers[lang_code]:
                generated_forms = f(generated_forms, *input_args, **input_kwargs)
            return generated_forms

        return decorate

    def apply_pregenerated_forms(self, lang_code, function):
        def decorate(*args, **kwargs):
            newargs = args
            newkwargs = kwargs
            f = self.pregenerators.get(lang_code, False)
            if f:
                newargs = f(*newargs, **newkwargs)
            return function(*newargs, **newkwargs)

        return decorate

    ##
    ### Here are the decorators
    ##

    def post_analysis_processor_for_iso(self, *language_isos):
        """For language specific processing after analysis is completed,
        for example, stripping tags before presentation to users.
        """

        def wrapper(postanalysis_function):
            for language_iso in language_isos:
                self.postanalyzers[language_iso].append(postanalysis_function)
                self.postanalyzers_doc[language_iso].append(
                    (postanalysis_function.__name__, postanalysis_function.__doc__)
                )
                print(
                    "%s overrides: registered post-analysis processor - %s"
                    % (language_iso, postanalysis_function.__name__)
                )

        return wrapper

    def pregenerated_form_selector(self, *language_isos):
        """The function that this decorates is used to select and
        construct a pregenerated paradigm for a given word and XML node.

        Only one may be defined.
        """

        def wrapper(pregenerated_selector_function):
            for language_iso in language_isos:
                self.pregenerators[language_iso] = pregenerated_selector_function
                self.pregenerators_doc[language_iso] = [
                    (
                        pregenerated_selector_function.__name__,
                        pregenerated_selector_function.__doc__,
                    )
                ]
                print(
                    "%s overrides: registered static paradigm selector - %s"
                    % (language_iso, pregenerated_selector_function.__name__)
                )

        return wrapper

    def tag_filter_for_iso(self, *language_isos):
        """Register a function for a language ISO"""

        def wrapper(restrictor_function):
            for language_iso in language_isos:
                self.registry[language_iso].append(restrictor_function)
                self.tag_filter_doc[language_iso].append(
                    (restrictor_function.__name__, restrictor_function.__doc__)
                )
                print(
                    "%s overrides: registered pregeneration tag filterer - %s"
                    % (language_iso, restrictor_function.__name__)
                )

        return wrapper

    def postgeneration_filter_for_iso(self, *language_isos):
        """Register a function for a language ISO"""

        def wrapper(restrictor_function):
            for language_iso in language_isos:
                self.postgeneration_processors[language_iso].append(restrictor_function)
                self.postgeneration_processors_doc[language_iso].append(
                    (restrictor_function.__name__, restrictor_function.__doc__)
                )
                print(
                    "%s overrides: registered entry context formatter - %s"
                    % (language_iso, restrictor_function.__name__)
                )

        return wrapper

    def __init__(self):
        from collections import defaultdict

        self.registry = defaultdict(list)
        self.tag_filter_doc = defaultdict(list)
        self.pregenerators = defaultdict(list)
        self.pregenerators_doc = defaultdict(list)
        self.postanalyzers = defaultdict(list)
        self.postanalyzers_doc = defaultdict(list)

        self.postgeneration_processors = defaultdict(list)
        self.postgeneration_processors["all"] = [word_generation_context]

        self.postgeneration_processors_doc = defaultdict(list)


generation_overrides = GenerationOverrides()


class XFST:
    def splitTagByCompound(self, analysis):
        _cmp = self.options.get("compoundBoundary")
        if not _cmp:
            return [analysis]
        is_cmp = "Cmp" in analysis
        # in order to obtain a better display for compounds a "dummy" tag
        # is needed for the last part of the analysis
        # Check if "Cmp" tag and if yes, split analysis and add
        # u'\u24D2'(= ⓒ ) to last part
        # If the last part of the analysis contains "Der" tag, split it
        # and add u'\u24D3'(= ⓓ ) to the first part and
        # u'\u24DB' (= ⓛ ) to the last part
        # Ex_1: miessemánnofeasta
        #   analysis_1 u'miessem\xe1nnu+N+Cmp/SgNom+Cmp#feasta+N+Sg+Nom'
        #   becomes: u'miessem\xe1nnu+N+Cmp/SgNom', u'feasta+N+Sg+Nom+\u24d2'
        # Ex_2: musihkkaalmmuheapmi
        #   analysis_1 = u'musihkka+N+Cmp/SgNom+Cmp#almmuheapmi+N+Sg+Nom'
        #   becomes = u'musihkka+N+Cmp/SgNom', u'almmuheapmi+N+Sg+Nom+\u24d2'
        #   analysis_2 = u'musihkka+N+Cmp/SgNom+Cmp#almmuhit+V+TV+Der/NomAct+N+Sg+Nom'
        #   becomes = u'musihkka+N+Cmp/SgNom', u'almmuhit+V+TV+\u24d3+Der/NomAct+N+Sg+Nom+\u24db'
        if isinstance(_cmp, list):
            for item in _cmp:
                if item in analysis:
                    analysis = analysis.split(item)
                    if is_cmp:
                        last_analysis = analysis[len(analysis) - 1]
                        analysis[len(analysis) - 1] = last_analysis + "+" + "\u24D2"
                        if "Der" in last_analysis:
                            ind_der = last_analysis.find("Der")
                            analysis[len(analysis) - 1] = (
                                last_analysis[0:ind_der]
                                + "\u24D3"
                                + "+"
                                + last_analysis[ind_der:]
                                + "+"
                                + "\u24DB"
                            )
            if isinstance(analysis, list):
                return analysis
            else:
                return [analysis]
        else:
            analysis = analysis.split(_cmp)
            if is_cmp:
                last_analysis = analysis[len(analysis) - 1]
                analysis[len(analysis) - 1] = last_analysis + "+" + "\u24D2"
                if "Der" in last_analysis:
                    ind_der = last_analysis.find("Der")
                    analysis[len(analysis) - 1] = (
                        last_analysis[0:ind_der]
                        + "\u24D3"
                        + "+"
                        + last_analysis[ind_der:]
                        + "+"
                        + "\u24DB"
                    )
            return analysis

    def tag_processor(self, analysis_line):
        """This is a default tag processor which just returns the
        wordform separated from the tag for a given line of analysis.

        You can write a function to replace this for an individual
        morphology by adding it to a file somewhere in the PYTHONPATH,
        and then setting the Morphology option `tagProcessor` to this path.

        Ex.)

            Morphology:
              crk:
                options:
                  tagProcessor: "configs/language_specific_rules/file.py:function_name"

        Note the colon. It may also be a good idea to write some tests
        in the docstring for that function. If these are present they
        will be quickly tested on launch of the service, and failures
        will prevent launch.

        A tag processor must accept a string as input, and return a
        tuple of the wordform and processed tag. You may do this to for
        example, re-order tags, or relabel them, but whateve the output
        is, it must be a string.

        For example:
            'wordform\tlemma+Tag+Tag+Tag' -> ('wordform', 'lemma+Tag+Tag+Tag')
        """

        wordform, lemma_tags, *weight = analysis_line.split("\t")

        if "?" in analysis_line:
            lemma_tags += "\t+?"

        if weight:
            return wordform, lemma_tags, weight
        else:
            # not true for saan - on the server (but not locally)
            # assert False, "all analysis lines in all the ways we do an analysis always contains the weight"
            return wordform, lemma_tags

    def clean(self, _output):
        """
        Clean XFST lookup text into

        [('keenaa', ['keen+V+1Sg+Ind+Pres', 'keen+V+3SgM+Ind+Pres']),
         ('keentaa', ['keen+V+2Sg+Ind+Pres', 'keen+V+3SgF+Ind+Pres'])]
        """

        analysis_chunks = [a for a in _output.split("\n\n") if a.strip()]

        cleaned = []
        for chunk in analysis_chunks:
            lemmas = []
            analyses = []
            weights = []

            for part in chunk.split("\n"):
                lemma, analysis, *weight = self.tag_processor(part)
                lemmas.append(lemma)
                analyses.append(analysis)
                if weight:
                    weights.append(weight[0])

            # anders: what does this do?
            lemma = list(set(lemmas))[0]
            cleaned.append((lemma, analyses, weights))

        return cleaned

    def _exec(self, _input, cmd, timeout=5):
        """Execute a process, but kill it after 5 seconds. Generally
        we expect small things here, not big things.
        """
        import subprocess

        try:
            lookup_proc = subprocess.Popen(
                cmd.split(" "),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError:
            raise Exception(
                "Error executing lookup command for this request, confirm "
                "that lookup utilities and analyzer files are present."
            )
        except Exception as e:
            raise Exception(f"Unhandled exception in lookup request: {e}")

        output, err = lookup_proc.communicate(_input, timeout=timeout)

        return output, err

    def load_tag_processor(self):
        import sys

        print("Loading the tag processor.")

        _path = self.options.get("tagProcessor")
        module_path, _, from_list = _path.partition(":")

        try:
            mod = imp.load_source(".", os.path.join(configs_path, module_path))
        except:
            sys.exit(f"Unable to import <{module_path}>")

        try:
            func = mod.__getattribute__(from_list)
        except:
            sys.exit(f"Unable to load <{from_list}> from <{module_path}>")

        self.tag_processor = func

    def __init__(self, lookup_tool, fst_file, ifst_file=False, options=None):
        self.cmd = f"{lookup_tool} -flags mbTT {fst_file}"
        self.options = options if isinstance(options, dict) else {}

        if ifst_file:
            self.icmd = f"{lookup_tool} -flags mbTT {ifst_file}"
        else:
            self.icmd = False

        if "tagProcessor" in self.options:
            self.load_tag_processor()

    def applyMorph(self, morph):
        morph.tool = self
        self.logger = morph.logger
        self.langcode = morph.langcode
        return morph

    def lookup(self, lookups_list):
        lookup_string = "\n".join(lookups_list)
        output, err = self._exec(lookup_string, cmd=self.cmd)
        if not output and err:
            name = self.__class__.__name__
            print(f"error when running tool:\n---\n{err}\n---")
            msg = f"{self.langcode} - {name}: {err}"
            self.logger.error(msg.strip())

        return self.clean(output), output, err

    def inverselookup_by_string(self, lookup_string):
        import sys

        if not self.icmd:
            print(" * Inverse lookups not available.", file=sys.stderr)
            return False

        output, err = self._exec(lookup_string, cmd=self.icmd)
        return self.clean(output), output, err

    def inverselookup(self, lemma, tags, no_preprocess_paradigm=False):
        if not no_preprocess_paradigm:
            lookup_string = self.get_inputstring(lemma, tags)
        else:
            lookup_string = tags

        return self.inverselookup_by_string(lookup_string)

    def get_inputstring(self, lemma, tags):
        """Make inputstring for inverselookup_by_string.

        Some templates (namely those where there are tags before the lemma),
        will cause problems. Thus if the lemma is  already in the tag, we
        consider this to be a completed tag string for generation. Otherwise,
        prefix the lemma then send to generation.
        """
        lookups_list = []
        for tag in tags:
            if isinstance(tag, str):
                tag = self.splitAnalysis(tag, inverse=True)
            if lemma in tag:
                combine = tag
            else:
                combine = [lemma] + tag
            lookups_list.append(self.formatTag(combine))

        return "\n".join(lookups_list)

    def tagUnknown(self, analysis):
        assert False, "unused?"
        return "+?" in analysis

    def tagStringToTag(self, parts, tagsets=None, inverse=False) -> Tag:
        tagsets = {} if tagsets is None else tagsets
        actio_with_tagsep = self.options.get("actio_tag", "Actio") + self.options.get(
            "tagsep", "+"
        )

        if inverse:
            delim = self.options.get("inverse_tagsep", self.options.get("tagsep", "+"))
        else:
            delim = self.options.get("tagsep", "+")
        if actio_with_tagsep in parts:
            # anders: this essentially checks if ("Actio+" is "in" `parts`),
            # and if it is, then `parts` must be a string already, because
            # otherwise, it would have been split up because of the "+" already
            tag = parts
            return Tag(tag, delim, tagsets=tagsets)
        else:
            # so, here, "Actio+" was not in `parts`, and therefore it is
            # concluded that we must take the tag delimeter, and join in all
            # the parts.
            # in other words, it has been determined that parts was a list
            tag = delim.join(parts)
            return Tag(tag, delim, tagsets=tagsets)

    def formatTag(self, parts, inverse=False):
        if inverse:
            delim = self.options.get("inverse_tagsep", self.options.get("tagsep", "+"))
        else:
            delim = self.options.get("tagsep", "+")
        return delim.join(parts)

    def splitAnalysis(self, analysis: str, inverse=False) -> list[str]:
        """'lemma+Tag+Tag+Tag' -> ['lemma', 'Tag', 'Tag', 'Tag']"""
        if inverse:
            delim = self.options.get("inverse_tagsep", self.options.get("tagsep", "+"))
        else:
            delim = self.options.get("tagsep", "+")
        return analysis.split(delim)


class HFST(XFST):
    def __init__(self, lookup_tool, fst_file, ifst_file=False, options=None):
        self.cmd = f"{lookup_tool} {fst_file}"
        self.icmd = f"{lookup_tool} {ifst_file}" if ifst_file else False
        self.options = {} if options is None else options

        if "tagProcessor" in self.options:
            self.load_tag_processor()


class PyHFST(XFST):
    """Same as HFST, but use the python bindings to libhfst directly, instead
    of subprocessing out to call the hfst- binaries."""

    def __init__(self, lookup_tool, fst_file, ifst_file=None, options=None):
        if not HAVE_PYHFST:
            raise Exception("hfst module not installed, cannot use PyHFST")

        self.options = {} if options is None else options

        # normally this is done in a loop, as in
        # https://hfst.github.io/python/3.11.0/classhfst_1_1HfstInputStream.html
        # but we know that there's only one transducer
        try:
            self.tr = hfst.HfstInputStream(fst_file).read()
        except NotTransducerStreamException:
            print(f"fatal: couldn't read fst_file ({fst_file=})", file=sys.stderr)
            raise

        if ifst_file is None:
            self.itr = None
        else:
            try:
                self.itr = hfst.HfstInputStream(ifst_file).read()
            except NotTransducerStreamException:
                sys.exit(f"fatal: couldn't read ifst_file ({ifst_file=})")

    def remove_flag_diacritics(self, line):
        return re.sub("@[^@]*@", "", line)

    def lookup(self, lookups_list):
        lookup_string = "\n".join(lookups_list)
        output = self.tr.lookup(lookup_string)

        lines = ""
        for line, _weight in output:
            lines += f"{lookup_string}\t{self.remove_flag_diacritics(line)}\n"

        return self.clean(lines + "\n\n"), lines, ""

    def inverselookup_by_string(self, lookup_string):
        if self.itr is None:
            print(" * Inverse lookups not available.")
            return False

        lines = ""
        for line in lookup_string.split("\n"):
            for results in self.itr.lookup(line):
                try:
                    output, _weight = results
                except ValueError:
                    # `results` is the list of outputs, which always is a
                    # 2-tuple of output and weight (I sincerely believe!)
                    assert False, "never happens"
                lines += f"{line}\t{self.remove_flag_diacritics(output)}\n\n"
        return self.clean(lines), lookup_string, ""

    def inverselookup(self, lemma, tags, no_preprocess_paradigm=False):
        if not no_preprocess_paradigm:
            lookup_string = self.get_inputstring(lemma, tags)
        else:
            lookup_string = tags

        return self.inverselookup_by_string(lookup_string)


class Morphology:
    def __init__(self, languagecode, tagsets=None):
        tagsets = {} if tagsets is None else tagsets
        self.tagsets = Tagsets(tagsets)

        self.langcode = languagecode

        self.generate = generation_overrides.apply_pregenerated_forms(
            languagecode, self.generate
        )
        self.generate = generation_overrides.restrict_tagsets(
            languagecode, self.generate
        )
        self.generate = generation_overrides.process_generation_output(
            languagecode, self.generate
        )

        self.lemmatize = generation_overrides.process_analysis_output(
            languagecode, self.morph_lemmatize
        )

        import logging

        logfile = logging.FileHandler("morph_log.txt")
        self.logger = logging.getLogger("morphology")
        self.logger.setLevel(logging.ERROR)
        self.logger.addHandler(logfile)

    def generate_to_objs(self, *args, **kwargs):
        # anders: args is (lemma, tagsets, lxml_element) ... right?
        # kwargs is {'extra_log_info':
        #   {'template_path': '/paradigms/sma/proper_nouns.paradigm'},
        #   'no_preprocess_paradigm': True}

        # TODO: occasionally lemma is not lemma, but first part of a
        # tag, need to fix with the tagsets
        # anders: yes! exactly what I'm running into now!

        def make_lemma(r):
            lems = []

            tag, forms = r
            if isinstance(forms, list):
                for f in forms:
                    lem = GeneratedForm(
                        tag, _input=f, tool=self.tool, tagsets=self.tagsets
                    )
                    lems.append(lem)
            else:
                lems = []
            return lems

        generate_out, stdin, stderr = self.generate(*args, **kwargs)
        generated = sum(list(map(make_lemma, generate_out)), [])
        return generated, stdin, stderr

    def generate(self, lemma, tagsets, node=None, pregenerated=None, **kwargs):
        """Run the lookup command, parse output into
        [(lemma, ['Verb', 'Inf'], ['form1', 'form2'])]

        If pregenerated, we pass the forms in using the same
        structure as the analyzed output. The purpose here is that
        pregenerated forms in lexicon may differ from language to
        language, and we want to allow processing for that to occur
        elsewhere.
        """

        if pregenerated:
            return pregenerated, "pregenerated", ""

        no_preprocess_paradigm = kwargs.get("no_preprocess_paradigm", False)
        res, raw_output, raw_errors = self.tool.inverselookup(
            lemma, tagsets, no_preprocess_paradigm=no_preprocess_paradigm
        )

        reformatted = []
        tag = False

        idxs = []
        for tag, forms, weights in res:
            indexes = [i for i, x in enumerate(weights) if x == min(weights)]
            idxs.append(indexes)
        updated_res = []
        for i in range(0, len(idxs)):
            # if not using weights idxs is an array of empty arrays
            forms = []
            new_res = []
            for idx in idxs[i]:
                forms.append(res[i][1][idx])
                new_res = (res[i][0], forms)
            if new_res:
                updated_res.append(new_res)
            else:
                updated_res.append([res[i][0], res[i][1]])

        for tag, forms in updated_res:
            unknown = False
            for f in forms:
                if "+?" in f:
                    unknown = True
                    # anders: added langcode to log message here
                    msg = (
                        f"({self.langcode}) "
                        + self.tool.__class__.__name__
                        + ": "
                        + tag
                        + "\t"
                        + "|".join(forms)
                    )
                    self.tool.logger.error(msg)

            if not unknown:
                reformatted.append((self.tool.splitAnalysis(tag, inverse=True), forms))
            else:
                parts = self.tool.splitAnalysis(tag, inverse=True)
                forms = False
                reformatted.append((parts, forms))

        # Log generation error:
        if len(reformatted) == 0:
            logg_args = [
                "GENERATE",
                self.langcode,
                tag or "",
            ]

            if len(tagsets) > 0:
                _tagsets = ",".join("+".join(t) for t in tagsets)
            else:
                _tagsets = ""
            logg_args.append(_tagsets)

            if "extra_log_info" in kwargs:
                _extra_log_info = kwargs.pop("extra_log_info")
                extra_log_info = ", ".join(
                    f"{k}: {v}" for (k, v) in _extra_log_info.items()
                )
                extra_log_info = extra_log_info
                logg_args.append(extra_log_info)

            logg = "\t".join(a for a in logg_args if a).strip()
            self.logger.error(logg)

        return reformatted, raw_output, raw_errors

    # start: morph_lemmatizer internal functions
    def remove_compound_analyses(self, analyses):
        cmp = self.tool.options.get("compoundBoundary")
        if cmp:
            indexes = [i for i, analysis in enumerate(analyses) if cmp in analysis]
            for index in reversed(indexes):
                del analyses[index]

    def remove_derivations(self, analyses):
        der = self.tool.options.get("derivationMarker")  # "Der/"
        if der:
            indexes = [i for i, analysis in enumerate(analyses) if der in analysis]
            for index in reversed(indexes):
                del analyses[index]

    @staticmethod
    def place_exact_lemmas_first(form: str, analyses: list[str]):
        """Given a list of analyses on the form "lemma+tag+tag+tag+...",
        re-arrange the analyses, so that the analyses which has a lemma with
        the exact form given in `form` is placed _before_ any other analyses.
        """
        # anders: A fix for #40 is to use the old code.

        # Another fix that seems to fix it, is to use
        # partition_in_place_stable() instead of partition_in_place()
        # The old code returns the list, which doesn't make sense when looking
        # at the caller of the code, which checks the return value of this
        # function for being == 0. That will _never_ happen if this function
        # returns a list. Using the partition_in_place_stable() fix, the caller
        # of this function also makes sense. See the lookups_to_lemma() method

        # OLD CODE: it only moves the first exact lemma,
        # even though the function is named "lemmas" (plural)
        # It also returns the `analyses` list. The caller of this function
        # (method lookups_to_lemma()) checks the return value against 0.
        # for index in range(0, len(analyses)):
        #     if form == analyses[index].split("+")[0]:
        #         analyses.insert(0, analyses[index])
        #         del analyses[index + 1]
        #         return analyses

        def lemma_eq_form(analysis):
            return analysis[0 : analysis.find("+")] == form

        n_exact_lemmas = partition_in_place_stable(analyses, lemma_eq_form)
        return n_exact_lemmas

    @staticmethod
    def place_longest_lemmas_first(form: str, analyses: list[str]):
        """Given a list of analyses on the form "lemma+tag+tag+tag+...",
        re-arrange the list so that the analysis with the longest lemma
        comes first, before all other analyses."""

        def lemma_len(line):
            i = line.find("+")
            return i if i >= 0 else len(line)

        longest = max(lemma_len(line) for line in analyses)
        partition_in_place(analyses, lambda line: lemma_len(line) == longest)

        # old code:
        # mystr = [
        #     len(analysis_line[0:analysis_line.find("+")])
        #     for analysis_line in analyses
        # ]
        # indmax = [index for index, j in enumerate(mystr) if j == max(mystr)]
        # if max(mystr) <= len(form):
        #     index2 = 0
        #     for index in range(0, len(indmax)):
        #         analyses.insert(index2, analyses.pop(indmax[index]))
        #         index2 += 1
        # return analyses

    # end: morph_lemmatizer internal functions

    def morph_lemmatize(
        self,
        form,
        split_compounds=False,
        non_compound_only=False,
        no_derivations=False,
    ):
        """Look up a wordform `form`, return a list of Lemmas"""
        lookups, raw_output, raw_errors = self.tool.lookup([form])

        if self.has_unknown(lookups):
            return [], raw_output, raw_errors

        lemmas = list(
            self.lookups_to_lemma(
                form,
                lookups,
                no_derivations,
                non_compound_only,
                split_compounds,
            )
        )

        return lemmas, raw_output, raw_errors

    def lookups_to_lemma(
        self, form, lookups, no_derivations, non_compound_only, split_compounds
    ):
        for _, analyses, _ in lookups:
            if non_compound_only:
                self.remove_compound_analyses(analyses)

            if no_derivations:
                self.remove_derivations(analyses)

            n_exact = self.place_exact_lemmas_first(form, analyses)

            if n_exact == 0:
                # no analyses lines had lemma exactly equal to the word form
                self.place_longest_lemmas_first(form, analyses)

            analyses = self.rearrange_on_count(analyses)

            if split_compounds:
                analyses = self.split_on_compounds(analyses)

            analyses_der_fin = self.make_analyses_der_fin(analyses)

            for analysis in analyses_der_fin:
                yield self.analysis_to_lemma(analysis, form)

    def analysis_to_lemma(self, analysis, wordform):
        analysis_parts = self.tool.splitAnalysis(analysis)
        lemma = ""

        if len(analysis_parts) == 1:
            actio_tag = self.tool.options.get("actio_tag", "Actio")
            actio_with_tagsep = actio_tag + self.tool.options.get("tagsep", "+")

            if actio_tag in analysis_parts[0]:
                try:
                    right_of_actio = analysis_parts[0].split(actio_tag)[1]
                except IndexError:  # An analysis might end in "+Actio"
                    right_of_actio = ""
                analysis_parts = [actio_with_tagsep + right_of_actio]
                lemma = analysis_parts
        else:
            # anders: logic: already established that len(analysis_parts) != 1,
            # so wordform = lemma, always
            # lemma = analysis_parts[0] if len(analysis_parts) == 1 else wordform
            lemma = wordform
        return Lemma(analysis_parts, _input=lemma, tool=self.tool, tagsets=self.tagsets)

    def make_analyses_der_fin(self, analyses):
        # anders: this turns
        # THIS:
        #  [
        #    'beaggin+N+Sg+Gen+Allegro',
        #    'beaggit+V+IV+Actio+Gen',
        #    'beaggit+V+IV+Actio+Nom',
        #    'beaggit+V+TV+Der/NomAct+N+Sg+Gen+Allegro',
        #    'beaggit+V+TV+Der/NomAct+N+Sg+Nom',
        #    'beaggin+N+Sg+Nom',
        #    'beaggi+N+NomAg+Ess',
        # ]
        # INTO THIS:
        # [
        #   'beaggin+N+Sg+Gen+Allegro',
        #   'beaggit+V+IV',
        #   'ActioGen',
        #   'ActioNom',
        #   'beaggit+V+TV',
        #   'Der/NomAct+N+Sg+Gen+Allegro',
        #   'Der/NomAct+N+Sg+Nom',
        #   'beaggin+N+Sg+Nom',
        #   'beaggi+N+NomAg+Ess',
        # ]

        analyses_der_fin = []
        default_tags = ("Dummy1", "Dummy2")
        tags = tuple(self.tool.options.get("tags_in_lexicon", default_tags))
        actio_tag = self.tool.options.get("actio_tag", "Actio")
        tagsep = self.tool.options.get("tagsep", "+")
        actio_with_tagsep = actio_tag + tagsep  # == "Actio+"

        for analysis in analyses:
            # replace "Actio+" with "Actio", to enable separate entries for
            # e.g. "Actio+Nom" and "Actio+Ess" in the dictionary
            analysis = analysis.replace(actio_with_tagsep, actio_tag)
            analysis_parts = analysis.split(tagsep)

            # Create list of analyses.
            # Each "tag", as in "tags_in_lexicon" (e.g. ["Der", "Comp", ...] in
            # sanit/sme), is a break point for creating a new analysis.
            # e.g. An analysis line such as
            #   "beaggit+V+TV+Der/NomAct+N+Sg+Gen+Allegro"
            # becomes
            #   ["beaggit+V+TV", "Der/NomAct+N+Sg+Gen+Allegro"]
            index = [
                index1
                for index1, part in enumerate(analysis_parts[1:], start=1)
                if part.startswith(tags)
            ]
            s = tagsep
            b = []
            if index:
                b.append(s.join(analysis_parts[: index[0]]))
                for previous, current in zip(index, index[1:]):
                    b.append(s.join(analysis_parts[previous:current]))
                b.append(s.join(analysis_parts[index[-1] : len(analysis_parts)]))
            else:
                b.append(analysis)

            analyses_der_fin.extend(b)

        return remove_duplicates(analyses_der_fin, keep_order=True)

    def split_on_compounds(self, analyses):
        return sum(list(map(self.tool.splitTagByCompound, analyses)), [])

    @staticmethod
    def rearrange_on_count(analyses: list[str]):
        """function name and overview of code seems like:
        this function rearranges the analyses, depending on how many Err/Orth
        each line has, and then how many Der each line has"""
        errorth_count = [analysis.count("Err/Orth") for analysis in analyses]

        any_without_errorth = min(errorth_count) == 0
        any_with_errorth = max(errorth_count) > 0
        max_1_errorth = max(errorth_count) == 1
        no_errorth = max(errorth_count) == 0

        if not (no_errorth or (any_without_errorth and max_1_errorth)):
            return analyses

        der_count = [analysis.count("Der") for analysis in analyses]
        any_without_der = min(der_count) == 0
        most_1_without_der = heapq.nsmallest(2, der_count)[-1] > 0
        all_has_der = min(der_count) > 0

        if len(analyses) >= 2 and any_without_der and most_1_without_der:
            line_without_der = analyses[der_count.index(0)]
            first_line_with_least_amount_of_der = analyses[
                der_count.index(heapq.nsmallest(2, der_count)[-1])
            ]
            return [line_without_der, first_line_with_least_amount_of_der]

        if no_errorth and max(der_count) <= 1:
            return analyses

        if all_has_der:
            first_line_with_least_amount_of_der = analyses[
                der_count.index(min(der_count))
            ]
            return [first_line_with_least_amount_of_der]

        if any_without_errorth and any_with_errorth:
            # remove the ones with Err/Orth
            idx = [i for i, x in enumerate(errorth_count) if x == 0]
            return [analyses[item] for item in idx]

        return analyses

    def has_unknown(self, lookups):
        # anders: I don't understand this. The function is called has_unknown.
        # Lets map it out:
        # Situation 1:
        #   None of the strings contains "?"
        #   Then the *"?" not in ..* will be True for all strings.
        #   Which means that *all()* will be True,
        #   so we return False
        # Situation 2:
        #   At least 1 string contains "?"
        #   Then the *"?" not in ..* will be be False for that string,
        #   which means that *all()* will be False,
        #   so we return True
        # Situation 3:
        #   All strings contains "?"
        #   Then the *"?" not in ..* fill be False for all strings,
        #   which means that *all()* will be False,
        #   so we return True
        # ...
        # So in the end, this is actually the same as any() with the check
        # inverted. I had to think this one out, in fear of refactoring
        # incorrectly. The double negating caught me completely off guard.
        former_result = not all(
            ["?" not in analysis for _, analyses, _ in lookups for analysis in analyses]
        )

        result = any(
            "?" in analysis for _, analyses, _ in lookups for analysis in analyses
        )

        assert result == former_result, "new code does the same as old code"
        return result
