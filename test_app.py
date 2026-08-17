import unittest, urllib.request, urllib.parse, http.cookiejar, sqlite3, os
BASE='http://127.0.0.1:8000'
class Flow(unittest.TestCase):
 def browser(self):
  jar=http.cookiejar.CookieJar(); return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 def post(self,op,path,data): return op.open(BASE+path,urllib.parse.urlencode(data).encode()).read().decode()
 def test_public_and_student(self):
  op=self.browser(); self.assertIn('Enroll Now',op.open(BASE+'/').read().decode())
  page=self.post(op,'/login',{'email':'student@storysprint.local','password':'Student123!'})
  self.assertIn('Student dashboard',page); self.assertIn('0 / 8 Lessons Completed',page)
  lesson=op.open(BASE+'/lesson/1').read().decode(); self.assertIn('Video coming soon',lesson)
  csrf=lesson.split('name="csrf" value="')[1].split('"')[0]
  page=self.post(op,'/lesson/1/complete',{'csrf':csrf}); self.assertIn('Completed',page)
  dash=op.open(BASE+'/dashboard').read().decode(); self.assertIn('1 / 8 Lessons Completed',dash)
 def test_admin_authorization_and_pages(self):
  op=self.browser(); page=self.post(op,'/login',{'email':'admin@storysprint.local','password':'Admin123!'})
  self.assertIn('Average progress',page)
  for p in ['/admin/modules','/admin/lessons','/admin/videos','/admin/resources','/admin/students','/admin/settings']:
   self.assertEqual(op.open(BASE+p).status,200,p)
  op2=self.browser(); self.post(op2,'/login',{'email':'student@storysprint.local','password':'Student123!'})
  with self.assertRaises(urllib.error.HTTPError) as e:op2.open(BASE+'/admin')
  self.assertEqual(e.exception.code,403)
if __name__=='__main__':unittest.main()
