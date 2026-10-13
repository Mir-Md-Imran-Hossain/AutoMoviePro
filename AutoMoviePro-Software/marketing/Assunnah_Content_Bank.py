import random
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

BANNER_DIR = r"E:\AI Assistant\Automations\Assunnah_Banners"

ISLAMIC_POSTS_ENGLISH = [
    # 1. Tawakkul (Surah At-Talaq 65:3)
    {
        "id": "banner_tawakkul",
        "banner": "banner_tawakkul.png",
        "title": "Tawakkul: Absolute Trust & Reliance in Allah",
        "text": """In the Name of Allah, the Most Gracious, the Most Merciful.

📖 Allah the Almighty declares in the Noble Qur'an:
وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ ۚ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ

"And whoever relies upon Allah — then He is sufficient for him. Indeed, Allah will accomplish His purpose."
— [Surah At-Talaq 65:3]

💡 Reflection & Living Faith:
Tawakkul is not passive resignation; it is active diligence of the limbs combined with total surrender of the heart. When every worldly door appears firmly shut, anchor your conviction in the Sustainer of all creation. Do your utmost, take the righteous means, and place the ultimate decree in Allah's Hands. The One Who orchestrates the galaxies will never abandon your prayers.

The Messenger of Allah ﷺ said:
"If you were to rely upon Allah with the required reliance, He would provide for you just as He provides for the birds: they go out in the morning with empty stomachs and return in the evening full."
— [Jami` at-Tirmidhi 2344, Sahih]

🤲 O Allah! Grant our hearts steadfast reliance upon You and serenity in Your divine decree. Ameen.

🌐 Official Portal: www.assunnahpath.com
✉️ Inquiries: assunnahpath@gmail.com
📘 Facebook: https://www.facebook.com/AsSunnahPathOfficial

#Quran #Hadith #Tawakkul #Faith #AsSunnahPath #IslamicWisdom #DailyVerse"""
    },

    # 2. Ease After Hardship (Surah Ash-Sharh 94:5-6)
    {
        "id": "banner_ease_after_hardship",
        "banner": "banner_ease_after_hardship.png",
        "title": "The Divine Promise: Ease After Hardship",
        "text": """In the Name of Allah, the Most Gracious, the Most Merciful.

📖 Allah the Exalted promises in the Glorious Qur'an:
فَإِنَّ مَعَ الْعُسْرِ يُسْرًا • إِنَّ مَعَ الْعُسْرِ يُسْرًا

"For indeed, with hardship [will be] ease. Indeed, with hardship [will be] ease."
— [Surah Ash-Sharh 94:5-6]

💡 Profound Tadabbur:
Notice the divine precision in the words: Allah does not state ease comes 'after' hardship, but 'with' it. Inside every trial lies the seeds of spiritual growth, elevation, and eventual triumph. In classical Arabic linguistics, 'al-usr' (hardship) is definite, while 'yusr' (ease) is repeated indefinitely—signifying that a single hardship can never overpower dual manifold ease.

Hold firm with patient endurance (Sabr). The darker the night, the closer the break of dawn.

🤲 O Allah! Remove our anxieties, grant relief to the oppressed, and open doors of light and mercy. Ameen.

🌐 Official Portal: www.assunnahpath.com
✉️ Inquiries: assunnahpath@gmail.com
📘 Facebook: https://www.facebook.com/AsSunnahPathOfficial

#QuranReflections #Patience #Sabr #Hope #AsSunnahPath #IslamicReminders"""
    },

    # 3. Seeking Sacred Knowledge (Sahih Muslim 2699)
    {
        "id": "banner_seeking_knowledge",
        "banner": "banner_seeking_knowledge.png",
        "title": "The Path to Paradise Through Sacred Knowledge",
        "text": """In the Name of Allah, the Most Gracious, the Most Merciful.

🎙️ The Messenger of Allah ﷺ proclaimed:
مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ

"Whoever travels a path in search of knowledge, Allah will make easy for him a path to Paradise."
— [Sahih Muslim 2699]

💡 The Noble Calling of Knowledge:
Seeking authentic Islamic knowledge purifies the intellect and anchors the soul in God-consciousness (Taqwa). The noble angels spread their wings in honoring humility for the seeker of knowledge, and every creation in the heavens and the earth supplicates for their forgiveness.

Make it an uncompromising daily discipline to understand at least one verse and one authentic prophetic tradition.

🤲 O Allah! Increase us in beneficial knowledge, grant us understanding of the Deen, and protect us from ignorance. Ameen.

🌐 Official Portal: www.assunnahpath.com
✉️ Inquiries: assunnahpath@gmail.com
📘 Facebook: https://www.facebook.com/AsSunnahPathOfficial

#Hadith #SahihMuslim #SacredKnowledge #Jannah #Sunnah #AsSunnahPath"""
    },

    # 4. Peace in the Remembrance of Allah (Surah Ar-Ra'd 13:28)
    {
        "id": "banner_remembrance_dhikr",
        "banner": "banner_remembrance_dhikr.png",
        "title": "Finding True Tranquility in Dhikr",
        "text": """In the Name of Allah, the Most Gracious, the Most Merciful.

📖 Allah the Almighty declares in His Noble Book:
الَّذِينَ آمَنُوا وَتَطْمَئِنُّ قُلُوبُهُم بِذِكْرِ اللَّهِ ۗ أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ

"Those who have believed and whose hearts are assured by the remembrance of Allah. Unquestionably, by the remembrance of Allah hearts are assured."
— [Surah Ar-Ra'd 13:28]

💡 The Sanctuary of the Heart:
In an era inundated with noise, anxiety, and temporal pursuits, human hearts yearn for authentic serenity. True peace is never found in transient wealth or worldly accolades; it is anchored exclusively in the continuous remembrance of Allah through Tasbeeh, Tahmeed, and sincere Istighfar.

When the heart remains tethered to the Creator, no worldly tempest can shake its foundation.

🤲 SubhanAllah, Alhamdulillah, La ilaha illa Allah, Allahu Akbar.

🌐 Official Portal: www.assunnahpath.com
✉️ Inquiries: assunnahpath@gmail.com
📘 Facebook: https://www.facebook.com/AsSunnahPathOfficial

#Dhikr #PeaceOfMind #RemembranceOfAllah #Quran #Serenity #AsSunnahPath"""
    }
]

ISLAMIC_POSTS_BANGLA = [
    # 1. তাওয়াক্কুল (সূরা আত-তালাক ৬৫:৩)
    {
        "id": "banner_tawakkul_bn",
        "banner": "banner_tawakkul_bn.png",
        "title": "তাওয়াক্কুল: মহান আল্লাহর ওপর অবিচল নির্ভরতা",
        "text": """بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ

📖 আল্লাহ সুবহানাহু ওয়া তা'আলা পবিত্র কুরআনে ইরশাদ করেন:
وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ ۚ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ

"আর যে ব্যক্তি আল্লাহর ওপর ভরসা করে, তার জন্য তিনিই যথেষ্ট। নিশ্চয় আল্লাহ তাঁর কাজ সম্পন্ন করবেনই।"
— [সূরা আত-তালাক ৬৫:৩]

💡 জীবনঘনিষ্ঠ প্রতিফলন ও শিক্ষা:
তাওয়াক্কুল বা আল্লাহর ওপর তাওয়াক্কুল রাখা মুমিনের আত্মার সবচেয়ে অপরাজেয় শক্তি। জীবনের কঠিনতম মুহূর্তে যখন প্রতিটি বাহ্যিক দরজা বন্ধ মনে হয়, তখন একাগ্র চিত্তে নিজের সব ভার আল্লাহর ওপর অর্পণ করুন। আপনি যথাসাধ্য সততা ও চেষ্টার মাধ্যমে পথ চলুন এবং চূড়ান্ত ফলাফল আল্লাহর হাতে সঁপে দিন। যিনি এই অসীম মহাবিশ্বের প্রতিটি অনু-পরমাণু নিয়ন্ত্রণ করছেন, তিনি কখনোই আপনার মঙ্গল ও প্রার্থনা ভুলে যান না।

রাসূলুল্লাহ ﷺ বলেছেন: "তোমরা যদি আল্লাহর ওপর যথাযথভাবে ভরসা করতে, তবে তিনি তোমাদের পাখিদের মতো রিজিক দিতেন—যারা সকালে খালি পেটে বের হয় এবং সন্ধ্যায় ভরা পেটে নীড়ে ফিরে আসে।" [তিরমিযী: ২৩৪৪, সহীহ]

🤲 হে আল্লাহ, আমাদের প্রতিটি পদক্ষেপে আপনার ওপর অবিচল আস্থা ও তাওয়াক্কুল রাখার তাওফিক দিন। আমিন।

🌐 বাংলা অফিসিয়াল পোর্টাল: www.assunnahpath.com/bangla
✉️ ইমেইল: assunnahpathbangla@gmail.com
📘 ফেসবুক পেজ: https://www.facebook.com/AsSunnahPathBangla

#কুরআন #হাদিস #তাওয়াক্কুল #ঈমান #আসসুন্নাহপাথবাংলা #ইসলামিকউক্তি #দৈনিকআমল"""
    },

    # 2. কষ্টের সাথেই স্বস্তি (সূরা আশ-শারহ ৯৪:৫-৬)
    {
        "id": "banner_ease_after_hardship_bn",
        "banner": "banner_ease_after_hardship_bn.png",
        "title": "ঐশী প্রতিশ্রুতি: কষ্টের সাথেই স্বস্তি রয়েছে",
        "text": """بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ

📖 আল্লাহ রব্বুল আলামীন পবিত্র কুরআনে ঘোষণা করেন:
فَإِنَّ مَعَ الْعُسْرِ يُسْرًا • إِنَّ مَعَ الْعُسْرِ يُسْرًا

"নিশ্চয় কষ্টের সাথেই স্বস্তি রয়েছে। অবশ্যই কষ্টের সাথেই স্বস্তি রয়েছে।"
— [সূরা আশ-শারহ ৯৪:৫-৬]

💡 গভীর তাদাব্বুর ও আত্মার সান্ত্বনা:
লক্ষণীয় বিষয় হলো, আয়াতে আল্লাহ সুবহানাহু ওয়া তা'আলা 'কষ্টের পরে' বলেননি, বরং বলেছেন 'কষ্টের সাথেই স্বস্তি রয়েছে'। অর্থাৎ প্রতিটি কঠিন পরিস্থিতির মাঝেই আল্লাহ তা'আলা মুক্তির বীজ ও কল্যাণের দ্বার উন্মুক্ত রাখেন। আরবি ব্যাকরণে 'আল-উসর' (কষ্ট) নির্দিষ্ট কিন্তু 'ইউসর' (স্বস্তি) অনির্দিষ্ট—যার অর্থ একটি কষ্ট কখনোই দুটি স্বস্তিকে পরাস্ত করতে পারে না।

ধৈর্য ধারণ করুন, আঁধার যত ঘনায় ভোরের আলো তত নিকটে আসে। আপনার রব আপনার অবস্থা সম্পর্কে সম্যক অবগত।

🤲 হে আল্লাহ, আমাদের জীবনের সকল অস্থিরতা ও বিপদ দূর করে শান্তির পথ উন্মোচন করে দিন। আমিন।

🌐 বাংলা অফিসিয়াল পোর্টাল: www.assunnahpath.com/bangla
✉️ ইমেইল: assunnahpathbangla@gmail.com
📘 ফেসবুক পেজ: https://www.facebook.com/AsSunnahPathBangla

#কুরআন #ধৈর্য #সবর #আসসুন্নাহপাথবাংলা #দ্বীনিজ্ঞান"""
    },

    # 3. দ্বীনি ইলম অন্বেষণ (সহীহ মুসলিম ২৬৯৯)
    {
        "id": "banner_seeking_knowledge_bn",
        "banner": "banner_seeking_knowledge_bn.png",
        "title": "সহজ জান্নাতের পথ: দ্বীনি জ্ঞান অন্বেষণ",
        "text": """بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ

🎙️ বিশ্বনবী রাসূলুল্লাহ সাল্লাল্লাহু আলাইহি ওয়া সাল্লাম ইরশাদ করেছেন:
مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ

"যে ব্যক্তি জ্ঞান অর্জনের উদ্দেশ্যে কোনো পথ অবলম্বন করে, আল্লাহ তার জন্য জান্নাতের পথ সহজ করে দেন।"
— [সহীহ মুসলিম ২৬৯৯]

💡 ইলমের মর্যাদা ও মুমিনের পাথেয়:
দ্বীনি জ্ঞান অর্জন করা আত্মিক মুক্তির সবচেয়ে মর্যাদাপূর্ণ ইবাদত। বিশুদ্ধ ইলম মানুষের অন্তর থেকে জাহেলিয়াত ও সংশয় দূর করে আল্লাহর খাঁটি ভয় (তাকওয়া) জাগ্রত করে। ইলম অন্বেষণকারীর সম্মানে ফেরেশতারা তাদের ডানা বিছিয়ে দেন এবং সৃষ্টিজগতের প্রতিটি সৃষ্টি তার জন্য ক্ষমা প্রার্থনা করে।

আসুন, প্রতিদিন অন্তত একটি আয়াত বা একটি সহীহ হাদিস অর্থ ও ব্যাখ্যাসহ অনুধাবন করার অভ্যাস গড়ে তুলি।

🤲 হে আল্লাহ, আমাদের উপকারী জ্ঞান (ইলমে নাফে') দান করুন এবং দ্বীনের সঠিক বুঝ দান করুন। আমিন।

🌐 বাংলা অফিসিয়াল পোর্টাল: www.assunnahpath.com/bangla
✉️ ইমেইল: assunnahpathbangla@gmail.com
📘 ফেসবুক পেজ: https://www.facebook.com/AsSunnahPathBangla

#হাদিস #সহীহমুসলিম #ইলম #জান্নাত #সুন্নাহ #আসসুন্নাহপাথবাংলা"""
    },

    # 4. আল্লাহর জিকিরে অন্তরের প্রশান্তি (সূরা আর-রাদ ১৩:২৮)
    {
        "id": "banner_remembrance_dhikr_bn",
        "banner": "banner_remembrance_dhikr_bn.png",
        "title": "অন্তরের খাঁটি প্রশান্তি কেবল আল্লাহর জিকিরেই",
        "text": """بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ

📖 আল্লাহ সুবহানাহু ওয়া তা'আলা পবিত্র কুরআনে ইরশাদ করেন:
الَّذِينَ آمَنُوا وَتَطْمَئِنُّ قُلُوبُهُم بِذِكْرِ اللَّهِ ۗ أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ

"যারা ঈমান এনেছে এবং আল্লাহর স্মরণে যাদের অন্তর প্রশান্ত হয়; জেনে রেখো, আল্লাহর স্মরণেই কেবল অন্তরসমূহ প্রশান্ত হয়।"
— [সূরা আর-রাদ ১৩:২৮]

💡 আত্মার চিরন্তন শান্তি:
আধুনিক জীবনের অস্থিরতায় মানুষ সর্বত্র মানসিক শান্তি খুঁজে বেড়ায়—সম্পদে, খ্যাতিতে কিংবা বৈষয়িক বিনোদনে। অথচ অন্তরের স্রষ্টা স্পষ্ট জানিয়ে দিয়েছেন, অন্তরের স্থায়ী শান্তি কেবল তাঁর স্মরণ ও জিকিরেই সুরক্ষিত। সুবহানাল্লাহ, আলহামদুলিল্লাহ, লা ইলাহা ইল্লাল্লাহ, আল্লাহু আকবারের মাধ্যমে প্রতিদিন নিজের আত্মাকে সজীব রাখুন।

🤲 হে আল্লাহ, আমাদের জিহ্বা ও অন্তরকে সর্বদা আপনার জিকির ও স্মরণে মুখরিত রাখুন। আমিন।

🌐 বাংলা অফিসিয়াল পোর্টাল: www.assunnahpath.com/bangla
✉️ ইমেইল: assunnahpathbangla@gmail.com
📘 ফেসবুক পেজ: https://www.facebook.com/AsSunnahPathBangla

#জিকির #আত্মিকশান্তি #কুরআন #আসসুন্নাহপাথবাংলা #আল্লাহরস্মরণ"""
    }
]

def get_dynamic_assunnah_post(language="en"):
    """
    Selects posts strictly by language:
    - 'en' for As-Sunnah Path Official Page & Profile
    - 'bn' for As-Sunnah Path Bangla Page
    """
    if language == "bn":
        post = random.choice(ISLAMIC_POSTS_BANGLA)
    else:
        post = random.choice(ISLAMIC_POSTS_ENGLISH)
        
    banner_path = os.path.join(BANNER_DIR, post["banner"])
    return post["text"], banner_path

if __name__ == "__main__":
    t_en, b_en = get_dynamic_assunnah_post("en")
    print("EN Banner:", b_en)
    print("EN Snippet:\n", t_en[:180])
    print("-" * 50)
    t_bn, b_bn = get_dynamic_assunnah_post("bn")
    print("BN Banner:", b_bn)
    print("BN Snippet:\n", t_bn[:180])
