"""Map a source-bound story build to the existing editable 4:5 producer.

This is a layout adapter, not an extractor for protected MotionGit code. The
official landscape project and the editable portrait have distinct identities.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path

from backlot import studio_dark_full as dark
from backlot.work_catalog import read_json, sha

CONTRACT = 'haike.native-story-portrait-input/1'
require = dark.require


def _file(row):
    require(isinstance(row, dict) and isinstance(row.get('path'), str), '模板文件绑定不完整')
    path = Path(row['path'])
    require(path.is_absolute() and path.is_file() and sha(path) == row.get('sha256'), '模板构建文件已变化或缺失')
    return path.resolve()


def _get(content, key, fallback=''):
    return content.get(key, fallback)


def content_map(build):
    a, b, c = (build['content'][key] for key in ('s01', 's04', 's08'))
    return {
        's01': {'kicker': _get(a, 'context'), 'headlineFirst': _get(a, 'claim.subject'),
                'headlineConnector': _get(a, 'claim.connector'), 'headlineAccent': _get(a, 'claim.destination'),
                'timelineTitle': _get(a, 'burden.heading'), 'wallMeta': _get(b, 'wall.attribution'),
                'statementFirst': _get(a, 'response.invitation'), 'statementSecond': _get(a, 'response.subject'),
                'payoffFirst': _get(a, 'response.connector'), 'payoffAccent': _get(a, 'response.conclusion')},
        's04': {'scopePrefix': _get(b, 'scope.connector'), 'scopeSubject': _get(b, 'scope.initial'),
                'scopeAccent': _get(b, 'scope.heading'), 'scopeConclusion': _get(b, 'scope.conclusion'),
                'categories': [_get(b, f'categories.{i}.label') for i in range(4)],
                'categoryNotes': [_get(b, f'categories.{i}.note') for i in range(4)],
                'wallMeta': _get(b, 'wall.attribution'), 'wallBadge': _get(b, 'wall.countLabel'),
                'wallFirst': _get(b, 'claim.line1'), 'wallSecond': _get(b, 'claim.line2'), 'wallAccent': _get(b, 'claim.line3'),
                'templateLine': _get(b, 'contrast.line1') + '\n' + _get(b, 'contrast.line2'),
                'templateChip': _get(b, 'template.label'), 'cameraPrefix': _get(b, 'lens.connector'),
                'cameraTitle': _get(b, 'lens.heading'),
                'cameraLabels': [_get(b, k) for k in ('lens.pushLabel', 'lens.trackLabel', 'lens.closeLabel')],
                'rhythmPrefix': '', 'rhythmTitle': _get(b, 'rhythm.heading'),
                'rhythmParts': [_get(b, f'rhythm.parts.{i}') for i in range(4)]},
        's08': {'reflectionContext': _get(c, 'reflection.context'), 'reflectionTop': _get(c, 'reflection.subject'),
                'reflectionBottom': _get(c, 'reflection.era'), 'reflectionConclusion': _get(c, 'reflection.conclusion'),
                'comparisonNote': _get(c, 'capacity.heading'),
                'comparisonLabels': [_get(c, 'capacity.opponentLabel'), _get(c, 'capacity.selfLabel')],
                'comparisonAction': _get(c, 'capacity.augmentationLabel'), 'capacityFactor': _get(c, 'capacity.factor', 3),
                'actionText': _get(c, 'action.heading'),
                'brandTitle': _get(c, 'brand.line1') + _get(c, 'brand.line2'),
                'brandDescription': _get(c, 'brand.description'), 'invitationHeading': _get(c, 'invitation.heading'),
                'invitationNote': _get(c, 'invitation.note'), 'signoff': _get(c, 'signoff'),
                'frameNote': _get(c, 'reaction.label')},
    }


def _review(row):
    review = deepcopy(row.get('review', {}))
    require(review.get('reviewed') is True and isinstance(review.get('description'), str)
            and review.get('review_evidence'), '真实素材缺少实际看帧记录')
    return review


def _text_gate(contents, fonts):
    """Use the actual bound font before a new title can enter a fixed slot."""
    from PIL import ImageFont
    def fit(text, size, width, label):
        font = ImageFont.truetype(str(fonts['display']), size)
        require(all(font.getlength(line) <= width for line in str(text).split('\n')),
                f'{label}超出4:5实际字框，请按本期语义缩写后重检')
    a, b, c = (contents[g] for g in ('s01', 's04', 's08'))
    for key, size, width in [('headlineFirst',96,750),('headlineConnector',110,750),('headlineAccent',126,750),
                              ('statementFirst',105,1264),('statementSecond',105,1264)]:
        fit(a[key],size,width,'开场文案')
    fit(a['payoffFirst']+a['payoffAccent'],144,1264,'开场结论')
    for line in [b['scopePrefix']+b['scopeSubject'], b['scopeAccent']+b['scopeConclusion']]:
        fit(line,82,1040,'四卡标题')
    fit(b['templateLine'],83,1264,'划线文案')
    for label, note in zip(b['categories'], b['categoryNotes']):
        display = ImageFont.truetype(str(fonts['display']),39)
        body = ImageFont.truetype(str(fonts['body']),21)
        require(display.getlength(label)+body.getlength(note)+32<=612,'四卡标签与说明超出字框，请缩写')
    fit(c['actionText'],48,730,'行动按钮')
    fit(c['brandTitle'],67,1090,'品牌标题')
    fit(c['brandDescription'],29,1160,'门店地址')


def convert(build):
    require(isinstance(build, dict) and build.get('schema') == 'haike.motion-native-content-build/1'
            and build.get('status') == 'built' and build.get('layout') == 'portrait45', '须先构建已验证的4:5模板输入')
    voice = _file(build['voice']); avatar = _file(build['avatar']); badge = _file(build['avatar']['badge'])
    require(build['avatar'].get('voice_sha256') == sha(voice), '人物与完整口播来源不同')
    proof = read_json(_file(build['avatar']['evidence']))
    verified = build['avatar'].get('validated_evidence', {})
    require(build['voice'].get('provenance', {}).get('authorized') is True
            and verified.get('source_voice_sha256') == sha(voice) and verified.get('video_sha256') == sha(avatar)
            and proof.get('full_decode') == 'passed'
            and proof.get('video_sha256', proof.get('sha256')) == sha(avatar), '构建未绑定已审核的完整同声源人物')
    caps_path = _file(build['captions'])
    require(build['captions'].get('voice_sha256') == sha(voice), '字幕与完整口播来源不同')
    raw_caps = read_json(caps_path)
    captions = [{'text': r['zh'], 'startMs': r['t0'] * 1000, 'endMs': r['t1'] * 1000} for r in raw_caps]
    frames = build['timeline']['frames']; seconds = build['timeline']['seconds']
    require(type(frames) is int and frames % 2 == 0 and abs(seconds - frames / 60) < 1e-8,
            '4:5总时钟必须同时对齐现有音频母带与60fps')
    sources = {'voice.wav': str(voice), 'presenter.mp4': str(avatar), 'badge.jpg': str(badge)}
    fonts = {role: role + '.ttf' for role in ('body', 'display')}
    for role, name in fonts.items(): sources[name] = str(_file(build['fonts'][role]))
    media, reviews = [], []

    def image(identity, row, review):
        path = _file(row); name = identity + path.suffix.lower()
        sources[name] = str(path)
        media.append({'id': identity, 'src': name, 'thumbnail': name, 'kind': 'image', 'offset': 0, 'fit': 'contain'})
        reviews.append({**review, 'id': identity, 'source_sha256': sha(path), 'thumbnail_sha256': sha(path)})
        return identity

    views = {r['id']: r for r in build['media']['wall']['views']}
    wall_ids = []
    for i, row in enumerate(build['media']['wall']['collages']):
        source_reviews = [_review(views[key]) for key in row['view_ids']]
        require(source_reviews, '素材墙拼图缺少源看帧记录')
        wall_ids.append(image('wall-' + str(i).zfill(2), row, {
            'reviewed': True, 'description': '源素材已实际查看，按构建清单拼图；布局另行实际预览。',
            'review_method': 'derived_from_reviewed_sources', 'source_reviews': source_reviews,
            'view_ids': row['view_ids']}))
    category_ids = [image('category-' + str(i), row, _review(row)) for i, row in enumerate(build['media']['categories'])]
    require(len(category_ids) == 4 and len(wall_ids) >= 3, '模板需要四张封面和真实素材墙')
    image('brand-badge', build['avatar']['badge'], {'reviewed': True, 'description': '同一已审数字人形象头像槽；证明见人物回执'})
    lens = build['media']['lens']; lens_path = _file(lens); lens_review = _review(lens)
    sources['lens' + lens_path.suffix.lower()] = str(lens_path)
    media.append({'id': 'lens', 'src': 'lens' + lens_path.suffix.lower(), 'thumbnail': media[len(wall_ids)]['thumbnail'],
                  'kind': 'video', 'offset': lens['offset'], 'fit': 'contain'})
    reviews.append({**lens_review, 'id': 'lens', 'source_sha256': sha(lens_path),
                    'thumbnail_sha256': sha(Path(sources[media[len(wall_ids)]['thumbnail']]))})
    contents = content_map(build)
    _text_gate(contents, {role: Path(sources[name]) for role,name in fonts.items()})
    shots = [{'id': group, 'group': group, 'title': build['short_title'], 'content': contents[group],
              'mediaIds': wall_ids if group != 's04' else ['lens', *category_ids[1:], *wall_ids],
              'mainMediaId': 'lens' if group == 's04' else wall_ids[0], 'weight': 3 if group == 's08' else 1}
             for group in ('s01', 's04', 's08')]
    scenes = dark.plan_shots(shots, frames, 60)
    category_scene = scenes[1]; start = math.floor(category_scene['cueTimes']['camera_demo'] * 60)
    length = category_scene['frames'] - start
    require(length / 60 <= lens['seconds'] + 1e-8, '镜头示范可见区间长于已审连续素材，请补更长素材')
    category_scene['videoWindows'] = [{'mediaId': 'lens', 'from': start, 'frames': length, 'offset': lens['offset']}]
    require(lens_review['source_start_seconds'] <= lens['offset']
            and lens['offset'] + length / 60 <= lens_review['source_end_seconds'] + .025, '镜头示范超出实际看帧区间')
    modes = []
    for scene in scenes:
        total = scene['frames']; base = scene['from']; cues = scene['cueTimes']
        spans = [(0, total, 'small')]
        if scene['group'] == 's01':
            at = round(cues['wall_handoff'] * 60); spans = [(0, at, 'large'), (at, total, 'small')]
        elif scene['group'] == 's08':
            a = round(cues['warning'] * 60); b = round(cues['call_to_action'] * 60)
            spans = [(0, a, 'large'), (a, b, 'small'), (b, total, 'large')]
        modes += [{'from': base + a, 'frames': b - a, 'mode': mode} for a, b, mode in spans if b > a]
    audio = {'voice': 'voice.wav', 'tailSeconds': seconds - build['voice']['clock']['duration_seconds'], 'sfx': []}
    if build.get('music'):
        music = build['music']; sources['music' + _file(music).suffix.lower()] = str(_file(music))
        audio.update(music='music' + _file(music).suffix.lower(), musicGainDb=music['gainDb'],
                     musicOffsetSeconds=music['offsetSeconds'], loopMusic=music['loop'])
    for key in ('tick', 'whoosh', 'dong'):
        path = _file(build['sfx'][key]); sources[key + '.wav'] = str(path)
    sound_cues = {'s01': [('title_slam','tick'),('strike','dong'),('wall_handoff','whoosh'),('payoff','tick')],
                  's04': [('category_1','tick'),('category_2','tick'),('category_3','tick'),('category_4','tick'),
                          ('wall_expand','whoosh'),('cross_out','dong'),('camera_demo','whoosh'),('narrative_arc','tick')],
                  's08': [('growth','tick'),('frame_work','tick'),('call_to_action','whoosh'),('comments','dong')]}
    for scene in scenes:
        for cue, sound in sound_cues[scene['group']]:
            audio['sfx'].append({'src': sound + '.wav', 'atSeconds': scene['from']/60 + scene['cueTimes'][cue],
                                 'gainDb': -20 if sound == 'tick' else -23})
    voice_sha = sha(voice)
    audio_names = {s['src'] for s in audio['sfx']} | ({audio['music']} if audio.get('music') else set())
    audio_reviews = {name: {'sha256': sha(Path(sources[name])), 'source': 'Explicit source-bound existing local audio; no generated provider call'} for name in audio_names}
    return {'title': build['title'] + ' · 原生动作4:5重排',
            'props': {'variant': 'native-story', 'brand': build['brand'], 'header': build['short_title'],
                      'footer': contents['s08']['brandDescription'], 'fontAssets': fonts, 'media': media,
                      'captions': captions, 'scenes': scenes, 'referencePortrait': 'badge.jpg',
                      'presenter': {'src': 'presenter.mp4', 'from': 0, 'frames': frames, 'offset': 0, 'modes': modes}},
            'sources': sources, 'audio': audio,
            'provenance': {'voice': {'source': 'same complete user-authorized input; see content-build identity',
                                     'authorized': True, 'sha256': voice_sha},
                           'captions': {'voice_sha256': voice_sha, 'method': 'source-bound native word boundaries'},
                           'audio': audio_reviews, 'media': reviews,
                           'presenterClips': [{'id': 'presenter', 'source_sha256': sha(avatar), 'voice_sha256': voice_sha,
                                               'reviewed': True, 'globalFrom': 0, 'sourceOffset': 0, 'frames': frames,
                                               'review_evidence': build['avatar']['evidence']['path']}]}}
