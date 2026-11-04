"""Bookend presenters and content-led material scenes; no effect-count quota."""

def story_policy(total,fps):
    seconds=total/fps
    return {'densityProfile':'concise' if seconds<=35 else 'standard' if seconds<=50 else 'expanded',
            'targetFrames':7*fps if seconds<=35 else 8*fps if seconds<=50 else 9*fps,
            'maxFrames':10*fps if seconds<=35 else 11*fps if seconds<=50 else 12*fps}


def validate_story(chapters,total,book,require):
    require(chapters and len(chapters)>=3,'首尾出镜模式至少需要开场、素材、结尾三个内容章节')
    require(chapters[0].get('role')=='intro' and chapters[-1].get('role')=='outro','首章role=intro，末章role=outro')
    require(all(c.get('role')=='material' for c in chapters[1:-1]),'数字人仅首尾出镜，中间章节role必须为material')
    fps=book['canvas']['fps'];policy=book['storyPolicy']
    for c in [chapters[0],chapters[-1]]:
        require(policy['bookendMinFrames']<=c['to']-c['from']<=policy['bookendMaxFrames'],'首尾各3至6秒，按内容明确分配，不能挤占素材段')
    for c in chapters:
        require(bool(c.get('headline')) and bool(c.get('intent')),'新模式每章填写短标题及叙事intent')
        if 'composition' in c:require(c['composition'] in policy['compositions'],'不支持的素材场景组合')
        labels=c.get('labels',['现场','互动'])
        require(isinstance(labels,list) and len(labels)==2 and all(isinstance(t,str) and 0<len(t)<=6 for t in labels),'对照标签为两个1至6字短标签')
    return [{'from':0,'to':chapters[0]['to']},{'from':chapters[-1]['from'],'to':total}]


def schedule_story(beats,book,total,require):
    policy=book['storyPolicy'];history=[]
    for beat in beats:
        role=beat['role'];intent=beat['intent']
        composition=beat.get('composition') or policy['intentComposition'][intent]
        if role!='material':composition='presenter'
        preferred=book['motionPolicy']['intents'][intent]
        if composition in {'duet','focus','orbit'}:
            primary={'duet':'parallax','focus':'click-open','orbit':'orbit'}[composition]
        else:
            # Intent wins; avoid only the immediately preceding material action.
            primary=next(m for m in preferred if m!=(history[-1] if history else None))
        if role=='material':history.append(primary)
        beat['composition']=composition
        beat['motions']={'03':{'mediaEffect':primary,
            'headlineEffect':'build' if intent in {'explain','recap'} else 'reveal',
            'conclusionEffect':'highlight' if intent in {'detail','compare'} else 'build'}}
        beat['readingHoldFrames']=max(0,beat['to']-beat['from']-book['canvas']['fps']*2)
    return {'presentation':'bookends','pilotVariant':'03','presenterWindows':[
        {'from':0,'to':beats[0]['to']},{'from':beats[-1]['from'],'to':total}],
        **story_policy(total,book['canvas']['fps'])}
