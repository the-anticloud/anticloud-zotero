> **DRAFT - MACHINE TRANSLATION (Argos Translate, offline). NOT FOR EXTERNAL USE. Pending native Arabic-speaker review.**

# The Inference-Efficient Road to Superintelligence

** عنوان العمل** توتّر سريع يُضْربُ مقياسَ قوةِ فاسدةِ.
**Status:** v0.1 DRAFT - argue sketch, not an empirical report.

## 1. Thesis

The Frontier strategy assumes superintelligence = more pretraining FLOPs.
نجادل بأنّ الدرب الأرخص هو التلألؤ الناقص
السبب والامتناع والمعايرة وتعني ما يقصده المشغل - باستخدام
أقل بكثير حساباً لكل قرار مفيد.

ويؤدي حجم القوة الشرائية إلى الحد الأقصى من الخسائر المرجعية. Sapient heuristics
تحقيق أقصى قدر من الإجراءات الصحيحة والمعايرة والمتعمدة لكل عملية من عمليات القوات المسلحة الليبرية.

## 2. Why scale-first is fragile

- Hoffmann et al. (2022) trained 400+ models (70M–16B params, 5B–500B
tokens) and found compute-optimal scaling scales params and tokens
وعلى نفس المنوال، فقد هزمت شينشيلا في السبعينيات بنماذج غير مدربة.
هذا هو نتيجة كفاءة التدريب، وليس دليلا على أن العملاق فقط
النماذج يمكن أن تكون سبباً
- Sardana et al. (2024) extend Chinchilla to include inference cost:
مع الطلب الكبير على المقارنات، يُدرَّب النموذج الأمثل
أطول (حتى الآلاف من الشارات/الشقائق من الناحية النظرية). الهيمنة
تكلفة الحياة - التقاطع الدقيق للـ TBD؛ علامة TBD.
- Replication work (Besiroglu et al. 2024) widens uncertainty around the
(ب) نسبة رمزية/فقرة بالضبط (المجموعة الدقيقة من TBD). إن الاتجاه قوي:
وكثير من نماذج الحدود كانت غير مدربة تدريبا كافيا. لا يرخص
تريليون-FLOP inevitability.

## 3. Sapient heuristics (summary)

مفصّلة في FRAMEWORK.md. خمس سوائل: التحلل، الامتناع،
معايرة، والتحقق، وشبه القصد. كل حرف
في حساب المقارنات لإجراء تخفيضات كبيرة في تكلفة الخطأ وفي الحاجة إلى إعادة التدريب.

## 4. Two alignments, not one

- **Epistemic alignment:** what a system may claim, with what certainty,
وعندما يجب أن تمتنع انظر EPISTEMIC ALIGNMENT.md.
- **Morphemic alignment:** whether output meaning matches operator intent
(الرخصة، النطاق، الفرضية، السجل). انظر:
القدرة بدون كليهما هي المسؤولية

## 5. Minimal-resource path without human bias

نحن لا نعني إزالة القيم البشرية. نحن نَعْني إزالة البشر
القطع الأثرية*: الضوضاء الشروحية، البدانة، صغرى الأغلبية.
مسار: مهام صغيرة يمكن التحقق منها، سلاسل التحقق الذاتي s شبكات فرعية
. distilled students . quantized deployment. كل خطوة قابلة للمراجعة
ويظهر العمل بالتذكرة اللوتري (Frankle &quot; Carbin 2019) وجود شبكات كثيفة
&apos; 1` تصفية الشبكات الفرعية التي يمكن تدريبها (10-20 في المائة على شبكة MNIST/CIFOR في الأصل؛
ويحتاج المتغيرات الواسعة النطاق إلى إعادة التوأم - TBD من أجل الألغام غير الألغام المضادة للأفراد. الفصل
(Hinton et al. 2015) compresses ensembles into deployable students.
الكمية (GPTQ/AWQ; Dettmers et al. 2023)
وفي كثير من البيئات القريبة من الفقد - التحلل الدقيق لمادة TBD لكل نموذج.

## 6. Against Aschenbrenner / SSI

- Aschenbrenner (Situational Awareness, June 2024) argues AGI ~2027 via
#0.5 OOM/yr compute + algorithmic + "unhobbling" gains,
إنفجار مخابرات و حكومة "مشروع"
نحن ننازع في عدم القابلية للاستمرار: الأوزان المفتوحة لم تتلاشى
تنافسيــة - رقم TBD الذي خلفه أشهر؛ مقاس الحد الأقصى ولكن موزع
متسع تسرّب قوّة وحشيّة؛ مجمّع الكفاءة.
- SSI (Sutskever/Gross/Levy 2024) states "safe superintelligence" as sole
المنتج، الأمان والقدرات جنبا إلى جنب، "على نطاق السلام".
نحن نتفق على القدرة على الأمان نحن نختلف على أن السلامة تتطلب
مركزي على نطاق العملاق أولا. صغيرة ومعايرة ومتعمدة
من الأسهل الإشراف على النظم، والأرخص إلى البخار الأحمر وقابلية النشر
في ظل قيود رأس المال السيادية. شاهدْ LIABILITY.md.

## 7. Liability-offset positioning

يُديرُ a يَكُونُ مُتَكَمِّنُ مُتَعَدَّدَاً مِنْ المُتَكَمِّنِيَة مِنْ المُخَلَفِيَةِ داخلي يُكلّفُ وقتَ هندسةِ،
ليس على نطاق مختبري استئجار GPU أو المسؤولية API. إذا فشلت، ستخسر أسابيع
إذا فشل الرهان العملاق (البيانات، السلامة، قفل البائعين)، تخسر
شركة انظر LIABILITY.md, IMPLEMENT.md, HANDBOK.md.

## 8. What would falsify this

- Sapient heuristics add latency without reducing costly errors.
- Sparse/distilled/quantized students cannot hold calibration on your
المهام العمودية.
- Epistemic abstention destroys UX value (users prefer fluent wrongness).
اختبروا الثلاثة في (أسس) قبل التقليص

## 9. Roadmap pointer

المسار المستقر في طريق RADMAP.md: معايرة →
انفصال كميّة عن "الإنتشار السيادي" لا حاجة للمختبر الخارجي

## 10. Citations

All grounded claims in CITATIONS.md with URLs. أي شيء بدون
مُعلّم بـ "تي بي دي".

## 11. Worked sketch (illustrative, TBD numbers)

- Baseline: open-weight model in 4-bit; measure accuracy, ECE, abstention rate (TBD values on your data).
- Add decomposition + verification: expect costly-error drop (TBD %); latency up (TBD ms).
- Distill to student (Hinton et al. 2015 pattern); check calibration holds (TBD delta).
- Report \$/verified-task before/after (TBD figures). No cross-lab generalization claimed.

## 12. Limitations

- Lottery-ticket evidence is strongest outside LLMs; LLM-scale tickets need rewinding (TBD method).
- Quantization near-lossless claims vary by model and benchmark (TBD per checkpoint).
- Calibration metrics (ECE/Brier) are dataset-sensitive (TBD bars).
- Sovereign deployment faces hardware supply and regulatory unknowns (TBD per region).
- This draft is an argument sketch; all ungrouded figures remain TBD per CITATIONS.md.

## 13. Call

إذا كنت تعمل تحت قيود رأسمالية، تشغيل الطريق الدائري في ROADMAP.md على عمودي واحد،
وحافظ على كل عدد لا يمكن التحقق منه مركبات الكفاءة؛
تأجير القوة

---
DRAFT 2026-10-16