import unittest
from exposure import history_exposure


class ExposureTests(unittest.TestCase):
    def test_name_boundary_sentence_and_initials(self):
        c=dict(name='Charles James Hogarth',aliases=['C. J. Hogarth','Hogarth'])
        a=history_exposure('The translator C. J. Hogarth is credited. The author is Turgenev.',
                           'Hogarth is mentioned. I will now discuss translation.',c)
        self.assertEqual(a['t1'],dict(exposed=1,role_in_same_sentence=1))
        self.assertEqual(a['t2'],dict(exposed=1,role_in_same_sentence=0))
        self.assertEqual(history_exposure('Hogarthian is not a surname mention.','',c)['exposed'],0)

    def test_possessive_and_no_semantic_reclassification(self):
        c=dict(name='Thomas Common',aliases=['Common',"Common's"])
        self.assertEqual(history_exposure('A common translation is discussed.','',c)['exposed'],1)
        self.assertEqual(history_exposure("COMMON’S translation is discussed.",'',c)['role_in_same_sentence'],1)


if __name__=='__main__':unittest.main()
