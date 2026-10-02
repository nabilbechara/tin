package main

import (
	"fmt"
	"strconv"
	"unicode"
)

func mix(h uint64, v uint64) uint64 {
	return (h ^ v) * 1099511628211
}

const seed uint64 = 14695981039346656037

func table(name string, t *unicode.RangeTable) {
	h := seed
	n := 0
	for r := 0; r < 205744; r++ {
		if unicode.Is(t, rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("table", name, n, h)
}

func sweepIsLetter() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsLetter(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsLetter", n, h)
}

func sweepIsDigit() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsDigit(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsDigit", n, h)
}

func sweepIsNumber() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsNumber(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsNumber", n, h)
}

func sweepIsSpace() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsSpace(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsSpace", n, h)
}

func sweepIsUpper() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsUpper(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsUpper", n, h)
}

func sweepIsLower() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsLower(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsLower", n, h)
}

func sweepIsTitle() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsTitle(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsTitle", n, h)
}

func sweepIsMark() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsMark(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsMark", n, h)
}

func sweepIsPunct() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsPunct(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsPunct", n, h)
}

func sweepIsSymbol() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsSymbol(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsSymbol", n, h)
}

func sweepIsControl() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsControl(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsControl", n, h)
}

func sweepIsGraphic() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsGraphic(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsGraphic", n, h)
}

func sweepIsPrint() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if unicode.IsPrint(rune(r)) {
			n++
			h = mix(h, uint64(r))
		}
	}
	fmt.Println("IsPrint", n, h)
}

func sweepToUpper() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		m := unicode.To(unicode.UpperCase, rune(r))
		if int(m) != r {
			n++
		}
		h = mix(h, uint64(m))
	}
	fmt.Println("ToUpper", n, h)
}

func sweepToLower() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		m := unicode.To(unicode.LowerCase, rune(r))
		if int(m) != r {
			n++
		}
		h = mix(h, uint64(m))
	}
	fmt.Println("ToLower", n, h)
}

func sweepToTitle() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		m := unicode.To(unicode.TitleCase, rune(r))
		if int(m) != r {
			n++
		}
		h = mix(h, uint64(m))
	}
	fmt.Println("ToTitle", n, h)
}

func sweepSimpleFold() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		m := unicode.SimpleFold(rune(r))
		if int(m) != r {
			n++
		}
		h = mix(h, uint64(m))
	}
	fmt.Println("SimpleFold", n, h)
}

func sweepQuote() {
	h := seed
	n := 0
	for r := 0; r <= 0x10ffff; r++ {
		if r >= 0xd800 && r <= 0xdfff {
			continue
		}
		q := strconv.Quote(string(rune(r)))
		if len(q) > 3 && q[1] == '\\' {
			n++
		}
		for i := 0; i < len(q); i++ {
			h = mix(h, uint64(q[i]))
		}
	}
	fmt.Println("quote", n, h, h)
}

func main() {
	fmt.Println("version", unicode.Version)
	sweepQuote()
	sweepIsLetter()
	sweepIsDigit()
	sweepIsNumber()
	sweepIsSpace()
	sweepIsUpper()
	sweepIsLower()
	sweepIsTitle()
	sweepIsMark()
	sweepIsPunct()
	sweepIsSymbol()
	sweepIsControl()
	sweepIsGraphic()
	sweepIsPrint()
	sweepToUpper()
	sweepToLower()
	sweepToTitle()
	sweepSimpleFold()
	fmt.Println("edge", unicode.IsLetter(-1), unicode.IsSpace(-1), unicode.IsPrint(0x110000), unicode.ToUpper(0x110000), unicode.ToLower(-5), unicode.SimpleFold(-5), unicode.SimpleFold(0x110000), unicode.To(7, 65), unicode.To(-1, 65), unicode.IsControl(-3))
	fmt.Println("orbit", unicode.SimpleFold(75), unicode.SimpleFold(107), unicode.SimpleFold(0x212a), unicode.SimpleFold(0x1e9e), unicode.SimpleFold(0xdf), unicode.SimpleFold(0x3a3), unicode.SimpleFold(0x3c2), unicode.SimpleFold(0x3c3))
	fmt.Println("oneof", unicode.In(0x4e16, unicode.Han, unicode.Latin), unicode.In(0x639, unicode.Han, unicode.Latin), unicode.In(65))
	table("C", unicode.Categories["C"])
	table("Cc", unicode.Categories["Cc"])
	table("Cf", unicode.Categories["Cf"])
	table("Cn", unicode.Categories["Cn"])
	table("Co", unicode.Categories["Co"])
	table("Cs", unicode.Categories["Cs"])
	table("L", unicode.Categories["L"])
	table("LC", unicode.Categories["LC"])
	table("Ll", unicode.Categories["Ll"])
	table("Lm", unicode.Categories["Lm"])
	table("Lo", unicode.Categories["Lo"])
	table("Lt", unicode.Categories["Lt"])
	table("Lu", unicode.Categories["Lu"])
	table("M", unicode.Categories["M"])
	table("Mc", unicode.Categories["Mc"])
	table("Me", unicode.Categories["Me"])
	table("Mn", unicode.Categories["Mn"])
	table("N", unicode.Categories["N"])
	table("Nd", unicode.Categories["Nd"])
	table("Nl", unicode.Categories["Nl"])
	table("No", unicode.Categories["No"])
	table("P", unicode.Categories["P"])
	table("Pc", unicode.Categories["Pc"])
	table("Pd", unicode.Categories["Pd"])
	table("Pe", unicode.Categories["Pe"])
	table("Pf", unicode.Categories["Pf"])
	table("Pi", unicode.Categories["Pi"])
	table("Po", unicode.Categories["Po"])
	table("Ps", unicode.Categories["Ps"])
	table("S", unicode.Categories["S"])
	table("Sc", unicode.Categories["Sc"])
	table("Sk", unicode.Categories["Sk"])
	table("Sm", unicode.Categories["Sm"])
	table("So", unicode.Categories["So"])
	table("Z", unicode.Categories["Z"])
	table("Zl", unicode.Categories["Zl"])
	table("Zp", unicode.Categories["Zp"])
	table("Zs", unicode.Categories["Zs"])
	table("Adlam", unicode.Scripts["Adlam"])
	table("Ahom", unicode.Scripts["Ahom"])
	table("Anatolian_Hieroglyphs", unicode.Scripts["Anatolian_Hieroglyphs"])
	table("Arabic", unicode.Scripts["Arabic"])
	table("Armenian", unicode.Scripts["Armenian"])
	table("Avestan", unicode.Scripts["Avestan"])
	table("Balinese", unicode.Scripts["Balinese"])
	table("Bamum", unicode.Scripts["Bamum"])
	table("Bassa_Vah", unicode.Scripts["Bassa_Vah"])
	table("Batak", unicode.Scripts["Batak"])
	table("Bengali", unicode.Scripts["Bengali"])
	table("Bhaiksuki", unicode.Scripts["Bhaiksuki"])
	table("Bopomofo", unicode.Scripts["Bopomofo"])
	table("Brahmi", unicode.Scripts["Brahmi"])
	table("Braille", unicode.Scripts["Braille"])
	table("Buginese", unicode.Scripts["Buginese"])
	table("Buhid", unicode.Scripts["Buhid"])
	table("Canadian_Aboriginal", unicode.Scripts["Canadian_Aboriginal"])
	table("Carian", unicode.Scripts["Carian"])
	table("Caucasian_Albanian", unicode.Scripts["Caucasian_Albanian"])
	table("Chakma", unicode.Scripts["Chakma"])
	table("Cham", unicode.Scripts["Cham"])
	table("Cherokee", unicode.Scripts["Cherokee"])
	table("Chorasmian", unicode.Scripts["Chorasmian"])
	table("Common", unicode.Scripts["Common"])
	table("Coptic", unicode.Scripts["Coptic"])
	table("Cuneiform", unicode.Scripts["Cuneiform"])
	table("Cypriot", unicode.Scripts["Cypriot"])
	table("Cypro_Minoan", unicode.Scripts["Cypro_Minoan"])
	table("Cyrillic", unicode.Scripts["Cyrillic"])
	table("Deseret", unicode.Scripts["Deseret"])
	table("Devanagari", unicode.Scripts["Devanagari"])
	table("Dives_Akuru", unicode.Scripts["Dives_Akuru"])
	table("Dogra", unicode.Scripts["Dogra"])
	table("Duployan", unicode.Scripts["Duployan"])
	table("Egyptian_Hieroglyphs", unicode.Scripts["Egyptian_Hieroglyphs"])
	table("Elbasan", unicode.Scripts["Elbasan"])
	table("Elymaic", unicode.Scripts["Elymaic"])
	table("Ethiopic", unicode.Scripts["Ethiopic"])
	table("Georgian", unicode.Scripts["Georgian"])
	table("Glagolitic", unicode.Scripts["Glagolitic"])
	table("Gothic", unicode.Scripts["Gothic"])
	table("Grantha", unicode.Scripts["Grantha"])
	table("Greek", unicode.Scripts["Greek"])
	table("Gujarati", unicode.Scripts["Gujarati"])
	table("Gunjala_Gondi", unicode.Scripts["Gunjala_Gondi"])
	table("Gurmukhi", unicode.Scripts["Gurmukhi"])
	table("Han", unicode.Scripts["Han"])
	table("Hangul", unicode.Scripts["Hangul"])
	table("Hanifi_Rohingya", unicode.Scripts["Hanifi_Rohingya"])
	table("Hanunoo", unicode.Scripts["Hanunoo"])
	table("Hatran", unicode.Scripts["Hatran"])
	table("Hebrew", unicode.Scripts["Hebrew"])
	table("Hiragana", unicode.Scripts["Hiragana"])
	table("Imperial_Aramaic", unicode.Scripts["Imperial_Aramaic"])
	table("Inherited", unicode.Scripts["Inherited"])
	table("Inscriptional_Pahlavi", unicode.Scripts["Inscriptional_Pahlavi"])
	table("Inscriptional_Parthian", unicode.Scripts["Inscriptional_Parthian"])
	table("Javanese", unicode.Scripts["Javanese"])
	table("Kaithi", unicode.Scripts["Kaithi"])
	table("Kannada", unicode.Scripts["Kannada"])
	table("Katakana", unicode.Scripts["Katakana"])
	table("Kawi", unicode.Scripts["Kawi"])
	table("Kayah_Li", unicode.Scripts["Kayah_Li"])
	table("Kharoshthi", unicode.Scripts["Kharoshthi"])
	table("Khitan_Small_Script", unicode.Scripts["Khitan_Small_Script"])
	table("Khmer", unicode.Scripts["Khmer"])
	table("Khojki", unicode.Scripts["Khojki"])
	table("Khudawadi", unicode.Scripts["Khudawadi"])
	table("Lao", unicode.Scripts["Lao"])
	table("Latin", unicode.Scripts["Latin"])
	table("Lepcha", unicode.Scripts["Lepcha"])
	table("Limbu", unicode.Scripts["Limbu"])
	table("Linear_A", unicode.Scripts["Linear_A"])
	table("Linear_B", unicode.Scripts["Linear_B"])
	table("Lisu", unicode.Scripts["Lisu"])
	table("Lycian", unicode.Scripts["Lycian"])
	table("Lydian", unicode.Scripts["Lydian"])
	table("Mahajani", unicode.Scripts["Mahajani"])
	table("Makasar", unicode.Scripts["Makasar"])
	table("Malayalam", unicode.Scripts["Malayalam"])
	table("Mandaic", unicode.Scripts["Mandaic"])
	table("Manichaean", unicode.Scripts["Manichaean"])
	table("Marchen", unicode.Scripts["Marchen"])
	table("Masaram_Gondi", unicode.Scripts["Masaram_Gondi"])
	table("Medefaidrin", unicode.Scripts["Medefaidrin"])
	table("Meetei_Mayek", unicode.Scripts["Meetei_Mayek"])
	table("Mende_Kikakui", unicode.Scripts["Mende_Kikakui"])
	table("Meroitic_Cursive", unicode.Scripts["Meroitic_Cursive"])
	table("Meroitic_Hieroglyphs", unicode.Scripts["Meroitic_Hieroglyphs"])
	table("Miao", unicode.Scripts["Miao"])
	table("Modi", unicode.Scripts["Modi"])
	table("Mongolian", unicode.Scripts["Mongolian"])
	table("Mro", unicode.Scripts["Mro"])
	table("Multani", unicode.Scripts["Multani"])
	table("Myanmar", unicode.Scripts["Myanmar"])
	table("Nabataean", unicode.Scripts["Nabataean"])
	table("Nag_Mundari", unicode.Scripts["Nag_Mundari"])
	table("Nandinagari", unicode.Scripts["Nandinagari"])
	table("New_Tai_Lue", unicode.Scripts["New_Tai_Lue"])
	table("Newa", unicode.Scripts["Newa"])
	table("Nko", unicode.Scripts["Nko"])
	table("Nushu", unicode.Scripts["Nushu"])
	table("Nyiakeng_Puachue_Hmong", unicode.Scripts["Nyiakeng_Puachue_Hmong"])
	table("Ogham", unicode.Scripts["Ogham"])
	table("Ol_Chiki", unicode.Scripts["Ol_Chiki"])
	table("Old_Hungarian", unicode.Scripts["Old_Hungarian"])
	table("Old_Italic", unicode.Scripts["Old_Italic"])
	table("Old_North_Arabian", unicode.Scripts["Old_North_Arabian"])
	table("Old_Permic", unicode.Scripts["Old_Permic"])
	table("Old_Persian", unicode.Scripts["Old_Persian"])
	table("Old_Sogdian", unicode.Scripts["Old_Sogdian"])
	table("Old_South_Arabian", unicode.Scripts["Old_South_Arabian"])
	table("Old_Turkic", unicode.Scripts["Old_Turkic"])
	table("Old_Uyghur", unicode.Scripts["Old_Uyghur"])
	table("Oriya", unicode.Scripts["Oriya"])
	table("Osage", unicode.Scripts["Osage"])
	table("Osmanya", unicode.Scripts["Osmanya"])
	table("Pahawh_Hmong", unicode.Scripts["Pahawh_Hmong"])
	table("Palmyrene", unicode.Scripts["Palmyrene"])
	table("Pau_Cin_Hau", unicode.Scripts["Pau_Cin_Hau"])
	table("Phags_Pa", unicode.Scripts["Phags_Pa"])
	table("Phoenician", unicode.Scripts["Phoenician"])
	table("Psalter_Pahlavi", unicode.Scripts["Psalter_Pahlavi"])
	table("Rejang", unicode.Scripts["Rejang"])
	table("Runic", unicode.Scripts["Runic"])
	table("Samaritan", unicode.Scripts["Samaritan"])
	table("Saurashtra", unicode.Scripts["Saurashtra"])
	table("Sharada", unicode.Scripts["Sharada"])
	table("Shavian", unicode.Scripts["Shavian"])
	table("Siddham", unicode.Scripts["Siddham"])
	table("SignWriting", unicode.Scripts["SignWriting"])
	table("Sinhala", unicode.Scripts["Sinhala"])
	table("Sogdian", unicode.Scripts["Sogdian"])
	table("Sora_Sompeng", unicode.Scripts["Sora_Sompeng"])
	table("Soyombo", unicode.Scripts["Soyombo"])
	table("Sundanese", unicode.Scripts["Sundanese"])
	table("Syloti_Nagri", unicode.Scripts["Syloti_Nagri"])
	table("Syriac", unicode.Scripts["Syriac"])
	table("Tagalog", unicode.Scripts["Tagalog"])
	table("Tagbanwa", unicode.Scripts["Tagbanwa"])
	table("Tai_Le", unicode.Scripts["Tai_Le"])
	table("Tai_Tham", unicode.Scripts["Tai_Tham"])
	table("Tai_Viet", unicode.Scripts["Tai_Viet"])
	table("Takri", unicode.Scripts["Takri"])
	table("Tamil", unicode.Scripts["Tamil"])
	table("Tangsa", unicode.Scripts["Tangsa"])
	table("Tangut", unicode.Scripts["Tangut"])
	table("Telugu", unicode.Scripts["Telugu"])
	table("Thaana", unicode.Scripts["Thaana"])
	table("Thai", unicode.Scripts["Thai"])
	table("Tibetan", unicode.Scripts["Tibetan"])
	table("Tifinagh", unicode.Scripts["Tifinagh"])
	table("Tirhuta", unicode.Scripts["Tirhuta"])
	table("Toto", unicode.Scripts["Toto"])
	table("Ugaritic", unicode.Scripts["Ugaritic"])
	table("Vai", unicode.Scripts["Vai"])
	table("Vithkuqi", unicode.Scripts["Vithkuqi"])
	table("Wancho", unicode.Scripts["Wancho"])
	table("Warang_Citi", unicode.Scripts["Warang_Citi"])
	table("Yezidi", unicode.Scripts["Yezidi"])
	table("Yi", unicode.Scripts["Yi"])
	table("Zanabazar_Square", unicode.Scripts["Zanabazar_Square"])
	table("ASCII_Hex_Digit", unicode.Properties["ASCII_Hex_Digit"])
	table("Bidi_Control", unicode.Properties["Bidi_Control"])
	table("Dash", unicode.Properties["Dash"])
	table("Deprecated", unicode.Properties["Deprecated"])
	table("Diacritic", unicode.Properties["Diacritic"])
	table("Extender", unicode.Properties["Extender"])
	table("Hex_Digit", unicode.Properties["Hex_Digit"])
	table("Hyphen", unicode.Properties["Hyphen"])
	table("IDS_Binary_Operator", unicode.Properties["IDS_Binary_Operator"])
	table("IDS_Trinary_Operator", unicode.Properties["IDS_Trinary_Operator"])
	table("Ideographic", unicode.Properties["Ideographic"])
	table("Join_Control", unicode.Properties["Join_Control"])
	table("Logical_Order_Exception", unicode.Properties["Logical_Order_Exception"])
	table("Noncharacter_Code_Point", unicode.Properties["Noncharacter_Code_Point"])
	table("Other_Alphabetic", unicode.Properties["Other_Alphabetic"])
	table("Other_Default_Ignorable_Code_Point", unicode.Properties["Other_Default_Ignorable_Code_Point"])
	table("Other_Grapheme_Extend", unicode.Properties["Other_Grapheme_Extend"])
	table("Other_ID_Continue", unicode.Properties["Other_ID_Continue"])
	table("Other_ID_Start", unicode.Properties["Other_ID_Start"])
	table("Other_Lowercase", unicode.Properties["Other_Lowercase"])
	table("Other_Math", unicode.Properties["Other_Math"])
	table("Other_Uppercase", unicode.Properties["Other_Uppercase"])
	table("Pattern_Syntax", unicode.Properties["Pattern_Syntax"])
	table("Pattern_White_Space", unicode.Properties["Pattern_White_Space"])
	table("Prepended_Concatenation_Mark", unicode.Properties["Prepended_Concatenation_Mark"])
	table("Quotation_Mark", unicode.Properties["Quotation_Mark"])
	table("Radical", unicode.Properties["Radical"])
	table("Regional_Indicator", unicode.Properties["Regional_Indicator"])
	table("STerm", unicode.Properties["STerm"])
	table("Sentence_Terminal", unicode.Properties["Sentence_Terminal"])
	table("Soft_Dotted", unicode.Properties["Soft_Dotted"])
	table("Terminal_Punctuation", unicode.Properties["Terminal_Punctuation"])
	table("Unified_Ideograph", unicode.Properties["Unified_Ideograph"])
	table("Variation_Selector", unicode.Properties["Variation_Selector"])
	table("White_Space", unicode.Properties["White_Space"])
}
