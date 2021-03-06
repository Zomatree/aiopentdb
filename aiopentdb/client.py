"""
MIT License

Copyright (c) 2020 CyCanCode

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import base64
import collections
import html
import urllib.parse
from typing import Dict, List, Optional, Union

import aiohttp
import yarl

from .enums import CategoryType, Encoding, Difficulty, QuestionType
from .errors import InvalidParameter, NoResults, RequestError, TokenEmpty, TokenNotFound
from .objects import Category, Count, GlobalCount, Question

__all__ = ('Client',)

_category_names = (
    'General Knowledge',
    'Entertainment: Books',
    'Entertainment: Film',
    'Entertainment: Music',
    'Entertainment: Musicals & Theatres',
    'Entertainment: Television',
    'Entertainment: Video Games',
    'Entertainment: Board Games',
    'Science & Nature',
    'Science: Computers',
    'Science: Mathematics',
    'Mythology',
    'Sports',
    'Geography',
    'History',
    'Politics',
    'Art',
    'Celebrities',
    'Animals',
    'Vehicles',
    'Entertainment: Comics',
    'Science: Gadgets',
    'Entertainment: Japanese Anime & Manga',
    'Entertainment: Cartoon & Animations'
)
_category_enums = (
    CategoryType.general_knowledge,
    CategoryType.books,
    CategoryType.film,
    CategoryType.music,
    CategoryType.musicals_and_theatres,
    CategoryType.television,
    CategoryType.video_games,
    CategoryType.board_games,
    CategoryType.nature,
    CategoryType.computers,
    CategoryType.mathematics,
    CategoryType.mythology,
    CategoryType.sports,
    CategoryType.geography,
    CategoryType.history,
    CategoryType.politics,
    CategoryType.art,
    CategoryType.celebrities,
    CategoryType.animals,
    CategoryType.vehicles,
    CategoryType.comics,
    CategoryType.gadgets,
    CategoryType.anime_and_manga,
    CategoryType.cartoon_and_animations
)

_category_by_names = {}
_category_by_ids = {}
for _name, _enum in zip(_category_names, _category_enums):
    _category = Category(_name, _enum.value, _enum)
    _category_by_names[_name] = _category
    _category_by_ids[_enum.value] = _category

_decoders = {
    Encoding.url: urllib.parse.unquote,
    Encoding.base64: lambda decodable: base64.b64decode(decodable).decode()
}
_fields = (
    'category',
    'correct_answer'
)
_enum_fields = (
    ('type', QuestionType),
    ('difficulty', Difficulty)
)

_errors = {
    1: NoResults,
    2: InvalidParameter,
    3: TokenNotFound,
    4: TokenEmpty
}


class Client:
    """Class for interacting with OpenTDB API and handling caches.

    Parameters
    ----------
    session: Optional[:class:`aiohttp.ClientSession`]
        Session to use for all HTTP requests.
        Defaults to ``aiohttp.ClientSession(raise_for_status=True)``.

    Attributes
    ----------
    session: :class:`aiohttp.ClientSession`
        Session to use for all HTTP requests.
    """

    _BASE_URL = yarl.URL('https://opentdb.com')

    def __init__(self, session: Optional[aiohttp.ClientSession] = None) -> None:
        self.session: aiohttp.ClientSession = session or aiohttp.ClientSession(raise_for_status=True)
        self._token = None
        self._questions = collections.deque(maxlen=50)
        self._categories = {}
        self._counts = {}
        self._global_counts = {}

    async def populate_cache(self) -> None:
        """|async|

        Populates all internal caches.
        """

        methods = (
            self.populate_token,
            self.populate_questions,
            self.populate_categories,
            self.populate_counts,
            self.populate_global_counts
        )
        for method in methods:
            await method()

    # Session

    async def _fetch(self, endpoint, *args, **kwargs):
        async with self.session.get(self._BASE_URL / endpoint, *args, **kwargs) as response:
            data = await response.json()
        if data is None:
            raise RequestError('Unable to fetch')

        response_code = data.pop('response_code', 0)
        if response_code != 0:
            raise _errors[response_code]
        return data

    async def close(self) -> None:
        """|async|

        Closes the internal session.
        """

        await self.session.close()

    # Token

    @property
    def token(self) -> Optional[str]:
        """Optional[:class:`str`]: Current session token."""

        return self._token

    async def fetch_token(self) -> str:
        """|async|

        Fetches a new session token.

        Returns
        -------
        :class:`str`
            New session token.
        """

        parameters = {'command': 'request'}
        data = await self._fetch('api_token.php', params=parameters)
        return data['token']

    async def populate_token(self) -> None:
        """|async|

        Populates the internal session token.
        """

        if self._token is None:
            self._token = await self.fetch_token()

    async def reset_token(self, token: Optional[str] = None) -> str:
        """|async|

        Resets a session token.

        Parameters
        ----------
        token: Optional[:class:`str`]
            Session token to reset.
            If not set, defaults to :attr:`token` and it will be replaced by the new session token.

        Returns
        -------
        :class:`str`
            New session token.
        """

        parameters = {
            'command': 'reset',
            'token': token or self._token
        }
        data = await self._fetch('api_token.php', params=parameters)

        new_token = data['token']
        if token is None:
            self._token = new_token
        return new_token

    # Question

    @property
    def questions(self) -> List[Question]:
        """List[:class:`.Question`]: List of cached questions."""

        return list(self._questions)

    async def fetch_questions(
        self,
        amount: int = 10,
        category_type: Optional[CategoryType] = None,
        difficulty: Optional[Difficulty] = None,
        question_type: Optional[QuestionType] = None,
        encoding: Optional[Encoding] = None,
        token: Optional[str] = None
    ) -> List[Question]:
        """|async|

        Fetches questions.

        Parameters
        ----------
        amount: :class:`int`
            Amount of question to fetch.
            Must be between ``1`` and ``50``.
            Defaults to ``10``.
        category_type: Optional[:class:`.CategoryType`]
            Type of the question category to fetch.
        difficulty: Optional[:class:`.Difficulty`]
            Difficulty of the question to fetch.
        question_type: Optional[:class:`.QuestionType`]
            Type of the question to fetch.
        encoding: Optional[:class:`.Encoding`]
            Encoding of the response to use when fetching.
        token: Optional[:class:`str`]
            Session token to use when fetching.

        Returns
        -------
        List[:class:`.Question`]
            List of fetched questions.
        """

        if amount < 1 and amount > 50:
            raise ValueError("'amount' must be between 1 and 50")

        parameters = {'amount': amount}
        if category_type is not None:
            parameters['category'] = category_type.value
        if difficulty is not None:
            parameters['difficulty'] = difficulty.value
        if question_type is not None:
            parameters['type'] = question_type.value
        if encoding is not None:
            parameters['encode'] = encoding.value
        if token is None:
            if self._token is not None:
                parameters['token'] = self._token
        else:
            parameters['token'] = token
        data = await self._fetch('api.php', params=parameters)

        questions = []
        decoder = _decoders.get(encoding, html.unescape)
        for entry in data['results']:
            entry['content'] = decoder(entry.pop('question'))
            for field in _fields:
                entry[field] = decoder(entry[field])

            incorrect_answers = entry['incorrect_answers']
            for index, incorrect_answer in enumerate(incorrect_answers):
                incorrect_answers[index] = decoder(incorrect_answer)

            entry['category'] = _category_by_names[entry['category']]
            for field, enum in _enum_fields:
                entry[field] = enum(decoder(entry[field]))

            questions.append(Question(**entry))
        return questions

    async def populate_questions(
        self,
        category_type: Optional[CategoryType] = None,
        difficulty: Optional[Difficulty] = None,
        question_type: Optional[QuestionType] = None,
        encoding: Optional[Encoding] = None,
        token: Optional[str] = None
    ) -> None:
        """|async|

        Populates the internal question cache.

        Parameters
        ----------
        category_type: Optional[:class:`.CategoryType`]
            Type of the question category to fetch.
        difficulty: Optional[:class:`.Difficulty`]
            Difficulty of the question to fetch.
        question_type: Optional[:class:`.QuestionType`]
            Type of the question to fetch.
        encoding: Optional[:class:`.Encoding`]
            Encoding of the response to use when fetching.
        token: Optional[:class:`str`]
            Session token to use when fetching.
        """

        questions = self._questions
        amount = questions.maxlen - len(questions)
        if amount < 1:
            return

        new_questions = await self.fetch_questions(
            amount, category_type, difficulty, question_type, encoding, token
        )
        questions.extend(new_questions)

    def get_questions(
        self,
        amount: int = 10,
        category_type: Optional[CategoryType] = None,
        difficulty: Optional[Difficulty] = None,
        question_type: Optional[QuestionType] = None,
    ) -> List[Question]:
        """Retrieves questions from the internal cache. This also removes them from the cache.

        Parameters
        ----------
        amount: :class:`int`
            Amount of question to fetch.
            Must be between ``1`` and ``50``.
            Defaults to ``10``.
        category_type: Optional[:class:`.CategoryType`]
            Type of the question category to fetch.
        difficulty: Optional[:class:`.Difficulty`]
            Difficulty of the question to fetch.
        question_type: Optional[:class:`.QuestionType`]
            Type of the question to fetch.

        Returns
        -------
        List[:class:`.Question`]
            List of cached questions.
        """

        actual_questions = self._questions
        retrieved_questions = []
        count = 0
        for question in self.questions:
            if count >= amount:
                break

            if (
                category_type is not None
                and question.category.type != category_type
            ):
                continue

            if (
                difficulty is not None
                and question.difficulty != difficulty
            ):
                continue

            if (
                question_type is not None
                and question.type != question_type
            ):
                continue

            actual_questions.remove(question)
            retrieved_questions.append(question)
            count += 1
        return retrieved_questions

    # Category

    @property
    def categories(self) -> List[Category]:
        """List[:class:`.Category`]: List of cached categories."""

        return list(self._categories.values())

    async def fetch_categories(self) -> Dict[CategoryType, Category]:
        """|async|

        Fetches all categories.

        Returns
        -------
        Dict[:class:`.CategoryType`, :class:`.Category`]
            Dict of fetched categories.
        """

        data = await self._fetch('api_category.php')

        categories = {}
        for entry in data['trivia_categories']:
            type = CategoryType(entry['id'])
            entry['type'] = type
            categories[type] = Category(**entry)
        return categories

    async def populate_categories(self) -> None:
        """|async|

        Populates the internal category cache.
        """

        if not self._categories:
            self._categories = await self.fetch_categories()

    def get_category(
        self,
        category_type: CategoryType
    ) -> Optional[Category]:
        """Retrieves a category from the internal cache.

        Parameters
        ----------
        category_type: :class:`.CategoryType`
            Type of the category to retrieve.

        Returns
        -------
        Optional[:class:`.Category`]
            Cached category.
        """

        return self._categories.get(category_type)

    # Count

    @property
    def counts(self) -> List[Count]:
        """List[:class:`.Count`]: List of cached counts."""

        return list(self._counts.values())

    async def fetch_count(
        self,
        category_type: CategoryType
    ) -> Count:
        """|async|

        Fetches a count.

        Parameters
        ----------
        category_type: :class:`.CategoryType`
            Type of the category to fetch.

        Returns
        -------
        :class:`.Count`
            Fetched count.
        """

        parameters = {'category': category_type.value}
        data = await self._fetch('api_count.php', params=parameters)

        count = data['category_question_count']
        return Count(
            _category_by_ids[category_type.value],
            count['total_question_count'],
            count['total_easy_question_count'],
            count['total_medium_question_count'],
            count['total_hard_question_count']
        )

    async def populate_count(
        self,
        category_type: CategoryType
    ) -> None:
        """|async|

        Populates the internal count cache.

        Parameters
        ----------
        category_type: :class:`.CategoryType`
            Type of the category to populate.
        """

        count = self._counts
        if not count.get(category_type):
            count[category_type] = await self.fetch_count(category_type)

    async def fetch_counts(self) -> Dict[CategoryType, Count]:
        """|async|

        Fetches all counts.

        Returns
        -------
        Dict[:class:`.CategoryType`, :class:`.Count`]
            Dict of fetched counts.
        """

        count = {}
        for enum in _category_enums:
            count[enum] = await self.fetch_count(enum)
        return count

    async def populate_counts(self) -> None:
        """|async|

        Populates all internal count caches.
        """

        if not self._counts:
            self._counts = await self.fetch_counts()

    def get_count(
        self,
        category_type: CategoryType
    ) -> Optional[Count]:
        """Retrieves a count from the internal cache.

        Parameters
        ----------
        category_type: :class:`.CategoryType`
            Type of the category to retrieve.

        Returns
        -------
        Optional[:class:`.Count`]
            Cached count.
        """

        return self._counts.get(category_type)

    # Global Count

    @property
    def global_counts(self) -> List[GlobalCount]:
        """List[:class:`.GlobalCount`]: List of cached global counts."""

        return list(self._global_counts.values())

    async def fetch_global_counts(self) -> Dict[Union[CategoryType, str], GlobalCount]:
        """|async|

        Fetches all global counts.

        Returns
        -------
        Dict[Union[:class:`.CategoryType`, :class:`str`], :class:`.GlobalCount`]
            Dict of fetched global counts.
        """

        data = await self._fetch('api_count_global.php')
        global_count = {}

        overall_count = data['overall']
        global_count['overall'] = GlobalCount(
            'overall',
            overall_count['total_num_of_questions'],
            overall_count['total_num_of_pending_questions'],
            overall_count['total_num_of_verified_questions'],
            overall_count['total_num_of_rejected_questions']
        )

        categories = data['categories']
        for id, count in categories.items():
            category = _category_by_ids[int(id)]
            global_count[category.type] = GlobalCount(
                category,
                count['total_num_of_questions'],
                count['total_num_of_pending_questions'],
                count['total_num_of_verified_questions'],
                count['total_num_of_rejected_questions']
            )

        return global_count

    async def populate_global_counts(self) -> None:
        """|async|

        Populates the internal global count cache.
        """

        if not self._global_counts:
            self._global_counts = await self.fetch_global_counts()

    def get_global_count(
        self,
        category_type: Union[CategoryType, str]
    ) -> Optional[GlobalCount]:
        """Retrieves a global count from the internal cache.

        Parameters
        ----------
        category_type: Union[:class:`.CategoryType`, :class:`str`]
            Type of the category to retrieve.

        Returns
        -------
        Optional[:class:`.GlobalCount`]
            Cached global count.
        """

        return self._global_counts.get(category_type)
