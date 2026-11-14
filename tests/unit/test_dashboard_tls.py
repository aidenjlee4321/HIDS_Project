from unittest.mock import patch
import unittest
from api.tls_leaf import validated_context,TLSError

class PrivateValidationTests(unittest.TestCase):
 def test_private_staging_requires_real_and_effective_root(self):
  for real,effective in ((1000,1000),(0,1000),(1000,0)):
   with self.subTest(real=real,effective=effective),patch('api.tls_leaf.os.getuid',return_value=real),patch('api.tls_leaf.os.geteuid',return_value=effective),patch('api.tls_leaf._openssl') as openssl:
    with self.assertRaises(TLSError):validated_context('/unused/leaf.pem','/unused/leaf.key','a'*64,1,_private=True)
    openssl.assert_not_called()
 def test_private_flag_rejects_non_boolean_values(self):
  for value in (1,'true',None):
   with self.subTest(value=value),patch('api.tls_leaf._openssl') as openssl:
    with self.assertRaises(TLSError):validated_context('/unused/leaf.pem','/unused/leaf.key','a'*64,1,_private=value)
    openssl.assert_not_called()

if __name__=='__main__':unittest.main()
