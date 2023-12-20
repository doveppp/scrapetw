import json
import logging
import re
from typing import Iterable
import snscrape
from snscrape.modules.twitter import TwitterTweetScraper, _TwitterAPIType, _TwitterAPIScraper, _logger

_GUEST_TOKEN_VALIDITY = 9000
logging.basicConfig(level=logging.DEBUG)
# _logger.setLevel(logging.NOTSET)
# print(_logger.level)


class V2Base(_TwitterAPIScraper):
    def __init__(self, baseUrl, *, session=None, guestTokenManager=None, maxEmptyPages=0, **kwargs):
        super().__init__(baseUrl, guestTokenManager=guestTokenManager, maxEmptyPages=maxEmptyPages, **kwargs)
        if session is not None:
            self._session = session

    def _ensure_guest_token(self, url=None):
        if self._guestTokenManager.token is None:
            _logger.info("Retrieving guest token")
            r = self._get(self._baseUrl if url is None else url, responseOkCallback=self._check_guest_token_response)
            if match := re.search(
                r'document.cookie="gt=(\d+);',
                r.text,
            ):
                _logger.debug("Found guest token in HTML")
                self._guestTokenManager.token = match.group(1)
            if "gt" in r.cookies:
                _logger.debug("Found guest token in cookies")
                self._guestTokenManager.token = r.cookies["gt"]
            if not self._guestTokenManager.token:
                _logger.debug("No guest token in response")
                _logger.info("Retrieving guest token via API")
                r = self._post(
                    "https://api.twitter.com/1.1/guest/activate.json",
                    data=b"",
                    headers=self._apiHeaders,
                    responseOkCallback=self._check_guest_token_response,
                )
                o = r.json()
                if not o.get("guest_token"):
                    raise snscrape.base.ScraperException("Unable to retrieve guest token")
                self._guestTokenManager.token = o["guest_token"]
            assert self._guestTokenManager.token
        _logger.debug(f"Using guest token {self._guestTokenManager.token}")
        self._session.cookies.set(
            "gt",
            self._guestTokenManager.token,
            domain=".twitter.com",
            path="/",
            secure=True,
            expires=self._guestTokenManager.setTime + _GUEST_TOKEN_VALIDITY,
        )
        self._apiHeaders["x-guest-token"] = self._guestTokenManager.token


class V2TwitterTweetsScraper(V2Base):
    name = "twitter-tweets"

    def __init__(self, tweet_ids, **kwargs):
        self.tweet_ids = tweet_ids
        super().__init__(f"https://twitter.com/i/web/status/1737324434359202275", **kwargs)

    def get_items(self):
        for tweet_id in self.tweet_ids:
            try:
                yield self.get_item(tweet_id)
            except (KeyError,) as e:
                _logger.warning(f"Error scraping {tweet_id}: {e}")
                continue

    def get_item(self, tweet_id):
        paginationVariables = {
            "tweetId": tweet_id,
            "withCommunity": False,
            "includePromotedContent": False,
            "withVoice": False,
        }
        variables = paginationVariables.copy()
        features = {
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": False,
            "tweet_awards_web_tipping_enabled": False,
            "responsive_web_home_pinned_timelines_enabled": True,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "responsive_web_media_download_video_enabled": False,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_enhance_cards_enabled": False,
        }

        params = {"variables": variables, "features": features}
        url = "https://api.twitter.com/graphql/5GOHgZe-8U2j5sVHQzEm9A/TweetResultByRestId"
        instructionsPath = ["data", "threaded_conversation_with_injections_v2", "instructions"]
        obj = self._get_api_data(url, _TwitterAPIType.GRAPHQL, params=params, instructionsPath=instructionsPath)
        if not obj["data"]:
            return
        return self._graphql_timeline_tweet_item_result_to_tweet(obj["data"]["tweetResult"]["result"], tweetId=tweet_id)


class V2TwitterUsersScraper(V2Base):
    def __init__(self, usernames, **kwargs):
        super().__init__(f"https://twitter.com/elonmusk", **kwargs)
        self.usernames = usernames

    def get_entities(self):
        for username in self.usernames:
            try:
                yield self._get_entity(username)
            except (snscrape.base.ScraperException, snscrape.base.EntityUnavailable) as e:
                _logger.warning(f"Error scraping {username}: {e}")
                continue

    def _get_entity(self, username):
        self._ensure_guest_token()
        fieldName = "screen_name"
        endpoint = "https://twitter.com/i/api/graphql/pVrmNaXcxPjisIvKtLDMEA/UserByScreenName"

        variables = {fieldName: str(username), "withSafetyModeUserFields": True}
        features = {
            "blue_business_profile_image_shape_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "highlights_tweets_tab_ui_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": False,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
        obj = self._get_api_data(
            endpoint,
            _TwitterAPIType.GRAPHQL,
            params={"variables": variables, "features": features},
            instructionsPath=["data", "user"],
        )
        if not obj["data"] or "result" not in obj["data"]["user"]:
            raise snscrape.base.ScraperException("Empty response")
        if obj["data"]["user"]["result"]["__typename"] == "UserUnavailable":
            raise snscrape.base.EntityUnavailable("User unavailable")
        return self._graphql_user_results_to_user(obj["data"]["user"])


if __name__ == "__main__":
    # t = V2TwitterUsersScraper(["elonmusk"] * 2 + ["22222221231232222"])
    # for i in t.get_entities():
    #     print("==============")
    #     print(i)

    t = V2TwitterTweetsScraper(["1737324434359202275"] * 2 + ["22222221231232222"])
    for i in t.get_items():
        print("==============")
        print(i)
