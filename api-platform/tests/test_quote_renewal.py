from datetime import UTC, datetime, timedelta

from test_commerce import enable, fund, real_quote
from test_platform import key, submit


def test_renewal_retains_provider_price_and_single_quote_id(env):
    store,_,client,other,_,_,_=env
    vault=enable(store);fund(env);headers,_=key(client)
    q=real_quote(client,headers)
    with store.write() as db:
        original=dict(db.execute('SELECT * FROM gateway_quotes WHERE id=?',(q['id'],)).fetchone())
        db.execute('UPDATE gateway_quotes SET expires_at=? WHERE id=?',((datetime.now(UTC)-timedelta(minutes=1)).isoformat(),q['id']))
    vault.update('bailian',{'voice':'changed-after-quote'})
    other_headers,_=key(other)
    assert other.post('/v2/quotes/'+q['id']+'/renew',headers=other_headers,json={'confirmed':True}).status_code==404
    assert client.post('/v2/quotes/'+q['id']+'/renew',headers=headers,json={'confirmed':False}).status_code==422
    response=client.post('/v2/quotes/'+q['id']+'/renew',headers=headers,json={'confirmed':True})
    assert response.status_code==200
    renewed=response.json()
    assert all(renewed[k]==q[k] for k in ('id','model','price','quoted_usage','max_charge_micros'))
    with store.read() as db:
        row=dict(db.execute('SELECT * FROM gateway_quotes WHERE id=?',(q['id'],)).fetchone())
        assert all(row[k]==original[k] for k in ('snapshot','input_json','amount','price_id','created_at'))
    job=submit(client,headers,renewed).json()
    assert job['status']=='queued'
    accepted=client.post('/v2/quotes/'+q['id']+'/renew',headers=headers,json={'confirmed':True})
    assert accepted.status_code==200 and accepted.json()['id']==q['id']
    with store.read() as db:
        assert db.execute('SELECT count(*) FROM gateway_jobs WHERE quote_id=?',(q['id'],)).fetchone()[0]==1


def test_renewal_stops_after_24_hours_or_disabled_provider(env):
    store,_,client,_,_,_,_=env;vault=enable(store);headers,_=key(client)
    q=real_quote(client,headers)
    vault.update('bailian',{'enabled':False})
    response=client.post('/v2/quotes/'+q['id']+'/renew',headers=headers,json={'confirmed':True})
    assert response.status_code==409
    vault.update('bailian',{'enabled':True})
    with store.write() as db:
        db.execute('UPDATE gateway_quotes SET created_at=? WHERE id=?',((datetime.now(UTC)-timedelta(hours=25)).isoformat(),q['id']))
    response=client.post('/v2/quotes/'+q['id']+'/renew',headers=headers,json={'confirmed':True})
    assert response.status_code==409 and response.json()['error']['code']=='quote_too_old'
