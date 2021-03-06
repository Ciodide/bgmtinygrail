import itertools
import logging
import re
from typing import *

import requests

from ._helper import *
from .login import Login
from .model import *

logger = logging.getLogger('bgmd.api')

__all__ = (
    'user_info',
    'user_mono',
    'person_work_voice_character',
    'collect_mono',
    'erase_collect_mono',
    'character_collection',
    'character_detail',
    'inbox',
    'get_gh',
    'subject_character',
)

empty_session = requests.Session()

empty_session.cookies['chii_theme'] = 'light'
empty_session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0'


def user_info(uid: Optional[int] = None, username: Optional[str] = None) -> User:
    """Usage: ``user_info(123456) or user_info(username='no1xsyzy')``. Returns :class:`User` object."""
    return User(**empty_session.get(f"https://api.bgm.tv/user/{uid or username}").json())


def user_mono(user: User, monotype: Literal['both', 'character', 'person']) -> List[Union[Character, Person]]:
    assert monotype in {'both', 'character', 'person'}, 'no available mono type'
    if monotype == 'both':
        return user_mono(user, 'character') + user_mono(user, 'person')
    return [(Character if monotype == 'character' else Person)(id=int(link['href'].split("/")[-1]))
            for link in multi_page(empty_session.get, f"https://bgm.tv/user/{user.username}/mono/{monotype}",
                                   f"a.l[href^=\"/{monotype}/\"]")]


def person_work_voice_character(person: Person) -> List[Character]:
    from ..db.cache_character import get, put
    characters = get(f'cv/{person.id}')
    if characters is not None:
        return [Character(id=cid) for cid in characters]
    response = empty_session.get(f"https://bgm.tv/person/{person.id}/works/voice")
    soup = BeautifulSoup(response.content, 'html.parser')
    characters = [int(k[0])
                  for a in soup.find_all("a", {"class": "l"})
                  for m in [a['href']]
                  for k in [re.findall(r"/character/(\d+)", m)]
                  if k]
    put(f'cv/{person.id}', characters)
    return [Character(id=cid) for cid in characters]


def collect_mono(login: Login, character: Union[Character, int]):
    if isinstance(character, Character):
        cid = character.id
    else:
        cid = character
    logger.info(f"collecting character: {cid}")
    response = login.session.get(f"https://bgm.tv/character/{cid}/collect?gh={login.gh}", allow_redirects=False)
    logger.debug(f"{response.status_code=}, {response.headers['Location']=}")
    successful = response.status_code == 302 and response.headers['Location'].startswith('/character/')
    if successful:
        logger.info(f"Collected character: {cid}")
    else:
        logger.error(f"Failed in collecting character: {cid}")
    return successful


def erase_collect_mono(login: Login, character: Union[Character, int]):
    if isinstance(character, Character):
        cid = character.id
    else:
        cid = character
    logger.info(f"removing collected character: {cid}")
    response = login.session.get(f"https://bgm.tv/character/{cid}/erase_collect?gh={login.gh}", allow_redirects=False)
    logger.debug(f"{response.status_code=}, {response.headers['Location']=}")
    successful = response.status_code == 302 and response.headers['Location'].startswith('/character/')
    if successful:
        logger.info(f"Removed collection: {cid}")
    else:
        logger.error(f"Failed in removing collection: {cid}")
    return successful


def character_collection(character: Union[Character, int]):
    if isinstance(character, Character):
        cid = character.id
    else:
        cid = character
    base_url = f"https://bgm.tv/character/{cid}/collections"
    return [h['href']
            for h in multi_page(empty_session.get, base_url, "a[href^=\"/user/\"]")]


def character_detail(character: Union[Character, int]):
    if isinstance(character, Character):
        cid = character.id
    else:
        cid = character
    url = f"https://bgm.tv/character/{cid}"
    response = empty_session.get(url)
    assert response.status_code == 200
    info = {}
    soup = BeautifulSoup(response.content, 'html.parser')
    if (name_el := soup.select_one("h1.nameSingle a[title]")) is not None:
        info['name'] = name_el.text
    if (large_image_el := soup.select_one("a.cover")) is not None:
        large = "https:" + large_image_el['href']
        info['images'] = Images(large=large,
                                medium=large.replace("/crt/l/", "/crt/m/"),
                                small=large.replace("/crt/l/", "/crt/s/"),
                                grid=large.replace("/crt/l/", "/crt/g/"))
    if (name_cn_el := soup.select_one("h1.nameSingle small")) is not None:
        info['name_cn'] = name_cn_el.text
    return Character(id=cid, url=url,
                     comment=len(soup.select("div[id^=\"post\"]")),
                     collects=len(character_collection(cid)),
                     **info)


def inbox(login: Login):
    links = [link.get('href')
             for link in multi_page_alt(login.session.get, "https://bgm.tv/pm/inbox.chii", "a[href^=\"/pm/view\"]")]
    link_origs = {}
    for link in links:
        redir_response = login.session.get(f"https://bgm.tv{link}", allow_redirects=False)
        if redir_response.status_code == 200:
            link_origs[link] = link
        elif redir_response.status_code == 302:
            link_origs[link] = redir_response.headers['Location']
    pg: Dict[int, Tuple[Optional[int], Optional[List], List]] = {}
    for link in set(link_origs.values()):
        head_pm_code = int(link[9:-5])
        bs = BeautifulSoup(login.session.get(f"https://bgm.tv{link}").content, 'html.parser')
        for el in bs.select(".text_pm"):
            pm_code = int(re.findall(r"^erasePM\('(\d+)", el.select_one("div.rr a")['onclick'])[0])
            pin = el.select_one("a.l[href^=\"/user/\"]")
            pm_content = [*itertools.dropwhile(lambda x: x is not pin, el.children)][1:]
            pin = el.select_one("hr.board")
            if pin is None:
                pm_content[0] = pm_content[0][2:]
                pg[pm_code] = (head_pm_code, None, pm_content)
            else:
                pm_title = [*pm_content[1].children]
                pm_content = pm_content[4:]
                pg[pm_code] = (None, pm_title, pm_content)
    return pg


def get_gh(login: Login):
    response = login.session.get("https://bgm.tv/character/1")
    soup = BeautifulSoup(response.content, 'html.parser')
    collector = soup.select_one('span.collect a')
    if collector is None:
        raise ValueError("Not login")
    from urllib.parse import urlsplit
    for kv in urlsplit(collector.attrs['href']).query.split('&'):
        k, v = kv.split('=', 1)
        if k == 'gh':
            return v


def subject_character(sub_id: int, *, login: Login = None):
    from ..db.cache_character import get, put
    characters = get(f'sub/{sub_id}')
    if characters is not None:
        return characters
    if login is None:
        session = empty_session
    else:
        session = login.session
    response = session.get(f"https://bgm.tv/subject/{sub_id}/characters")
    soup = BeautifulSoup(response.content, 'html.parser')
    characters = sorted({int(re.findall(r"/character/(\d+)", m.attrs['href'])[0]) for m in
                         soup.select("#columnInSubjectA a[href^=\"/character/\"]")})
    put(f'sub/{sub_id}', characters)
    return characters
