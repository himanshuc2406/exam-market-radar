import unittest

from core import analysis


class DoubtFilterTests(unittest.TestCase):
    def test_praise_with_samajh_is_not_a_doubt(self):
        text = "Sir me पहली bar math pad rahi hu or bahut ache se samjh aa raha h thank you so much sir ❤"
        self.assertFalse(analysis.looks_like_doubt(text))

    def test_question_praise_is_not_a_doubt(self):
        text = "Class bhot badiya thi sir questions best tha sara questions kr liya"
        self.assertFalse(analysis.looks_like_doubt(text))

    def test_easy_way_praise_is_not_a_doubt(self):
        text = "Sir aap math ke hard question bhi easy way me bata rahe hai thanks sir"
        self.assertFalse(analysis.looks_like_doubt(text))

    def test_real_hinglish_question_is_a_doubt(self):
        self.assertTrue(analysis.looks_like_doubt("Sir percentage kaise solve kare?"))

    def test_timestamp_alone_is_not_a_doubt(self):
        self.assertFalse(analysis.looks_like_doubt("12:35 best shortcut sir"))

    def test_timestamp_with_confusion_is_a_doubt(self):
        self.assertTrue(analysis.looks_like_doubt("12:35 par yeh step samajh nahi aaya"))


if __name__ == "__main__":
    unittest.main()
