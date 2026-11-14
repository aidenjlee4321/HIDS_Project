import concurrent.futures
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from api.pilot_sessions import Sessions, Denied, digest, closed_json

class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.s = Sessions(clock=lambda:self.now)
    def session(self):
        return self.s.redeem(self.s.mint())
    def test_grant_cannot_authorize(self):
        grant = self.s.mint()
        with self.assertRaises(Denied):self.s.authorize(grant)
    def test_single_use_and_separate_token(self):
        grant=self.s.mint();token=self.s.redeem(grant)
        self.assertNotEqual(grant,token);self.s.authorize(token)
        with self.assertRaises(Denied):self.s.redeem(grant)
        with self.assertRaises(Denied):self.s.redeem(token)
    def test_deadline_grant(self):
        grant=self.s.mint();self.now+=60
        with self.assertRaises(Denied):self.s.redeem(grant)
    def test_before_deadline_grant(self):
        grant=self.s.mint();self.now+=59.999;self.s.authorize(self.s.redeem(grant))
    def test_idle_boundary(self):
        token=self.session();self.now+=300
        with self.assertRaises(Denied):self.s.authorize(token)
    def test_idle_renewal_and_absolute_bound(self):
        token=self.session()
        for i in range(1,9):self.now=10+i*200;self.s.authorize(token)
        self.now=1810
        with self.assertRaises(Denied):self.s.authorize(token)
    def test_wrong_scope_does_not_authorize(self):
        token=self.session()
        with self.assertRaises(Denied):self.s.authorize(token,'events:read')
    def test_capacity_combines_sessions_and_grants(self):
        tokens=[self.session() for _ in range(2)];grants=[self.s.mint() for _ in range(2)]
        with self.assertRaises(Denied):self.s.mint()
        self.s.authorize(self.s.redeem(grants[0]));self.s.logout(tokens[0]);self.s.mint()
    def test_capacity_reclaims_expired(self):
        for _ in range(4):self.s.mint()
        self.now+=60;self.s.mint()
    def test_logout_and_revoke(self):
        t=self.session();self.s.logout(t)
        with self.assertRaises(Denied):self.s.authorize(t)
        t=self.session();g=self.s.mint();self.s.revoke_all()
        with self.assertRaises(Denied):self.s.authorize(t)
        with self.assertRaises(Denied):self.s.redeem(g)
    def test_restart(self):
        t=self.session()
        with self.assertRaises(Denied):Sessions().authorize(t)
    def test_concurrent_redemption(self):
        g=self.s.mint()
        def attempt(_):
            try:return self.s.redeem(g)
            except Denied:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:r=list(ex.map(attempt,range(20)))
        self.assertEqual(sum(x is not None for x in r),1)
    def test_random_failure_consumes_grant(self):
        g=self.s.mint();self.s._random=lambda _:b''
        with self.assertRaises(Denied):self.s.redeem(g)
        self.s._random=__import__('secrets').token_bytes
        with self.assertRaises(Denied):self.s.redeem(g)
    def test_random_collision_denies(self):
        self.s._random=lambda _:b'a'*32;g=self.s.mint()
        with self.assertRaises(Denied):self.s.redeem(g)
    def test_malformed_tokens(self):
        for t in ('','a'*42,'a'*44,'a'*42+'B','a'*42+'=','a'*42+'\n',None,{},123):
            with self.subTest(t=t),self.assertRaises(Denied):self.s.authorize(t)
    def test_clock_rollback_revokes(self):
        t=self.session();self.now-=1
        with self.assertRaises(Denied):self.s.authorize(t)
        self.now=20
        with self.assertRaises(Denied):self.s.authorize(t)
    def test_nonfinite_clock_refuses(self):
        t=self.session();self.now=float('nan')
        with self.assertRaises(Denied):self.s.authorize(t)
    def test_memory_retains_only_digests(self):
        t=self.session();g=self.s.mint()
        self.assertNotIn(t,repr(vars(self.s)));self.assertNotIn(g,repr(vars(self.s)))
    def test_closed_json(self):
        self.assertEqual(closed_json(b'{"version":1}',{'version'}),{'version':1})
        for data in (b'{"version":1,"version":1}',b'{}',b'[]',b'{"version":NaN}',b'{"version":1,"extra":1}',b'{',b'\xff'):
            with self.subTest(data=data),self.assertRaises(Denied):closed_json(data,{'version'})

if __name__=='__main__':unittest.main()
