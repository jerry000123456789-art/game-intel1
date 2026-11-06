import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus
import feedparser
import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DOCS = ROOT / 'docs'
CONFIG = ROOT / 'config' / 'sources.json'
DATA.mkdir(exist_ok=True)
DOCS.mkdir(exist_ok=True)
NOW = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
TZ = dt.timezone(dt.timedelta(hours=8))
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'GameIntelMonitor/1.0 (personal RSS monitoring)'})


def load_json(path, fallback):
    if not path.exists(): return fallback
    with path.open(encoding='utf-8') as f: return json.load(f)


def save_json(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def classify(text):
    s = text.lower()
    tags = []
    patterns = {
      '兌換碼': r'兌換碼|禮包碼|序號|兑换码|シリアルコード|クーポン|쿠폰|redeem.?code|promo.?code|gift.?code',
      '攻略': r'攻略|教學|新手|ガイド|攻略|공략|guide|walkthrough|build|tier list',
      '上市情報': r'上市|發售|上架|事前預約|事前登録|発売|출시|사전예약|release date|launch|upcoming|pre.register',
      '更新公告': r'更新|改版|版本|アップデート|업데이트|patch|update|maintenance'
    }
    for label, pattern in patterns.items():
        if re.search(pattern, s, flags=re.I): tags.append(label)
    return tags or ['一般情報']


def parsed_time(entry):
    for key in ('published_parsed', 'updated_parsed'):
        v = entry.get(key)
        if v:
            return dt.datetime.fromtimestamp(time.mktime(v), dt.timezone.utc).isoformat(timespec='seconds')
    return None


def feed_items(url, source, region):
    response = SESSION.get(url, timeout=25)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    if feed.bozo and not feed.entries:
        raise ValueError(str(feed.bozo_exception))
    result=[]
    for e in feed.entries[:40]:
        title = re.sub('<[^>]+>', '', e.get('title','')).strip()
        link = e.get('link','').strip()
        if not title or not link: continue
        summary = re.sub('<[^>]+>', ' ', e.get('summary','')).strip()[:1500]
        key = hashlib.sha256((source + '|' + (e.get('id') or link)).encode()).hexdigest()[:24]
        result.append({'id':key,'source':source,'region':region,'title':title,'url':link,
                       'summary':summary,'published_at':parsed_time(e),'tags':classify(title+' '+summary)})
    return result


def telegram(text):
    token=os.getenv('TELEGRAM_BOT_TOKEN','')
    chat=os.getenv('TELEGRAM_CHAT_ID','')
    if not token or not chat: return
    r=SESSION.post(f'https://api.telegram.org/bot{token}/sendMessage',
        json={'chat_id':chat,'text':text[:3900],'disable_web_page_preview':True}, timeout=20)
    r.raise_for_status()


def export_excel(items):
    wb=Workbook()
    ws=wb.active
    ws.title='情報總表'
    headers=['ID','類別','地區','來源','標題','摘要','發布時間 UTC','首次發現 UTC','最後檢查 UTC','最後異動 UTC','來源網址']
    ws.append(headers)
    for x in sorted(items, key=lambda x:x['first_seen_at'], reverse=True):
        ws.append([x['id'], ', '.join(x['tags']),x['region'],x['source'],x['title'],x['summary'],
                   x.get('published_at'),x['first_seen_at'],x['last_checked_at'],x['last_changed_at'],x['url']])
    ws.freeze_panes='A2'
    ws.auto_filter.ref=ws.dimensions
    widths=[27,22,14,24,55,75,26,26,26,26,65]
    from openpyxl.utils import get_column_letter
    for idx,width in enumerate(widths,1): ws.column_dimensions[get_column_letter(idx)].width=width
    for c in ws[1]:
        c.fill=PatternFill('solid',fgColor='17324D')
        c.font=Font(color='FFFFFF',bold=True)
    ws2=wb.create_sheet('異動歷史')
    ws2.append(['異動時間 UTC','情報 ID','異動類型','內容'])
    for e in load_json(DATA/'events.json',[]):
        ws2.append([e['at'],e['id'],e['type'],e.get('detail','')])
    ws2.freeze_panes='A2'
    for col,width in {'A':27,'B':27,'C':18,'D':90}.items(): ws2.column_dimensions[col].width=width
    wb.save(DOCS/'game_intel.xlsx')


def main():
    config=load_json(CONFIG,{})
    old=load_json(DATA/'items.json',[])
    by_id={x['id']:x for x in old}
    events=load_json(DATA/'events.json',[])
    collected=[]
    failures=[]
    feeds=[]
    for q in config.get('news_queries',[]):
        url='https://news.google.com/rss/search?q='+quote_plus(q['query'])+'&hl='+quote_plus(q['language'])+'&gl='+q['country']+'&ceid='+q['country']+':'+q['language'].split('-')[0]
        feeds.append((url,'Google News',q['region']))
    for f in config.get('rss_feeds',[]):
        feeds.append((f['url'],f.get('name','RSS'),f.get('region','全球')))
    for ch in config.get('youtube_channels',[]):
        channel_id=ch.get('channel_id','')
        if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',channel_id):
            failures.append('無效的 YouTube channel_id: '+channel_id)
            continue
        feeds.append(('https://www.youtube.com/feeds/videos.xml?channel_id='+channel_id,
                      'YouTube: '+ch.get('name',channel_id),'全球'))
    for url,name,region in feeds:
        try:
            collected.extend(feed_items(url,name,region))
        except Exception as exc:
            failures.append(name+' ('+region+'): '+str(exc)[:180])
    fresh=[]
    for item in collected:
        prior=by_id.get(item['id'])
        if prior:
            changed=any(prior.get(k)!=item.get(k) for k in ('title','summary','tags','published_at'))
            item['first_seen_at']=prior['first_seen_at']
            item['last_changed_at']=NOW if changed else prior['last_changed_at']
            if changed: events.append({'at':NOW,'id':item['id'],'type':'更新','detail':item['title']})
        else:
            item['first_seen_at']=NOW
            item['last_changed_at']=NOW
            fresh.append(item)
            events.append({'at':NOW,'id':item['id'],'type':'新增','detail':item['title']})
        item['last_checked_at']=NOW
        by_id[item['id']]=item
    # Keep historical items even when a feed no longer includes them.
    items=list(by_id.values())
    save_json(DATA/'items.json',items)
    save_json(DATA/'events.json',events)
    save_json(DOCS/'items.json',items)
    save_json(DOCS/'status.json',{'last_run_at':NOW,'feeds_checked':len(feeds),
        'items_seen':len(collected),'new_items':len(fresh),'failures':failures})
    export_excel(items)
    if fresh:
        top=fresh[:8]
        message='🎮 全球遊戲情報：新增 '+str(len(fresh))+' 筆\n\n'+'\n'.join('• '+x['title'][:75]+'\n'+x['url'] for x in top)
        if len(fresh)>8: message+='\n另有 '+str(len(fresh)-8)+' 筆，請查看儀表板。'
        try: telegram(message)
        except Exception as exc: print('Telegram error:',exc,file=sys.stderr)
    print(f'Checked {len(feeds)} feeds; got {len(collected)} items, {len(fresh)} new; failures={len(failures)}')
    for error in failures: print('WARNING:',error,file=sys.stderr)
    # Fail if every configured feed failed, so GitHub shows a failed run.
    if feeds and len(failures)>=len(feeds): sys.exit(1)

if __name__=='__main__': main()
