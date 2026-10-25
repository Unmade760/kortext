#!/usr/bin/env python3
"""
Generate benchmark fixtures for Kortext test suite:
1. tests/fixtures/hotpotqa_sample.json (50 items)
2. tests/fixtures/longmemeval_sample.json (50 items across 5 abilities)
3. tests/fixtures/kortext_golden_set.json (20 real codebase questions)
"""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------
# 1. HotpotQA Sample (50 items, 2-hop questions)
# ---------------------------------------------------------
hotpotqa_data = [
    {
        "id": "hotpot_001",
        "question": "Who directed the 2016 superhero film starring Benedict Cumberbatch as Stephen Strange?",
        "gold_passages": [
            "Scott Derrickson (born July 16, 1966) is an American filmmaker. He directed the Marvel Cinematic Universe film Doctor Strange (2016), as well as horror films such as Sinister and The Black Phone.",
            "Doctor Strange is a 2016 American superhero film based on the Marvel Comics character of the same name. Produced by Marvel Studios and distributed by Walt Disney Studios Motion Pictures, the film stars Benedict Cumberbatch as the title character Dr. Stephen Strange."
        ],
        "answer": "Scott Derrickson"
    },
    {
        "id": "hotpot_002",
        "question": "Which publication was founded earlier, Arthur's Magazine or First for Women?",
        "gold_passages": [
            "Arthur's Magazine was an American 19th-century literary magazine published in Philadelphia from 1844 to 1846. It was edited by Timothy Shay Arthur, the author of Ten Nights in a Bar-Room.",
            "First for Women is a woman's magazine published bi-weekly by the Bauer Media Group in Englewood Cliffs, New Jersey. The magazine was established in 1989 and focuses on health, nutrition, and relationships."
        ],
        "answer": "Arthur's Magazine"
    },
    {
        "id": "hotpot_003",
        "question": "What common medium do Werewolves on Wheels and Le Tombeur belong to?",
        "gold_passages": [
            "Werewolves on Wheels is a 1971 American exploitation action-horror film directed by Michel Levesque and starring Stephen Oliver, Donna Anders, and Billy Gray.",
            "Le Tombeur is a 1958 French comedy film directed by René Delacroix and starring Jacques Jouanneau, Raymond Bussières, and Marthe Mercadier."
        ],
        "answer": "film"
    },
    {
        "id": "hotpot_004",
        "question": "Which Athenian general led the Greek army to victory against the Persians in the 490 BC Battle of Marathon?",
        "gold_passages": [
            "The Battle of Marathon took place in September 490 BC during the first Persian invasion of Greece. It was fought between the citizens of Athens, aided by Plataea, and a Persian invasion force commanded by Datis and Artaphernes.",
            "Miltiades the Younger was an Athenian general who is best known for his tactical command at the Battle of Marathon in 490 BC, where his tactical encirclement led to the decisive defeat of the Persian forces."
        ],
        "answer": "Miltiades"
    },
    {
        "id": "hotpot_005",
        "question": "Which mathematician and logician, famous for formulating the Turing machine concept, developed early software for the Manchester Mark 1?",
        "gold_passages": [
            "Alan Turing (1912-1954) was an English mathematician, computer scientist, logician, and theoretical biologist. In 1936, he published his foundational paper introducing the theoretical model known as the Turing machine.",
            "The Manchester Mark 1 was one of the earliest stored-program electronic computers, built at the University of Manchester. Alan Turing joined the laboratory in 1948 and wrote the programmer's handbook for the system."
        ],
        "answer": "Alan Turing"
    },
    {
        "id": "hotpot_006",
        "question": "Which pastoral romance written by Thomas Lodge served as the principal source for William Shakespeare's As You Like It?",
        "gold_passages": [
            "As You Like It is a pastoral comedy by William Shakespeare believed to have been written in 1599. The play follows Rosalind as she flees persecution into the Forest of Arden.",
            "Rosalynde: Euphues Golden Legacie is a pastoral prose romance by English writer Thomas Lodge published in 1590. Shakespeare used Lodge's Rosalynde as the primary narrative source for his play As You Like It."
        ],
        "answer": "Rosalynde"
    },
    {
        "id": "hotpot_007",
        "question": "Which mathematician worked with Charles Babbage on the Analytical Engine and created what is recognized as the first computer algorithm?",
        "gold_passages": [
            "The Analytical Engine was a proposed mechanical general-purpose computer designed by English mathematician and inventor Charles Babbage, first described in 1837.",
            "Ada Lovelace (1815-1852) was an English mathematician and writer. While translating Luigi Menabrea's article on Babbage's Analytical Engine, she appended a set of notes containing an algorithm to calculate Bernoulli numbers, recognized as the first published computer program."
        ],
        "answer": "Ada Lovelace"
    },
    {
        "id": "hotpot_008",
        "question": "Who composed the musical score for Francis Ford Coppola's 1972 crime film The Godfather?",
        "gold_passages": [
            "The Godfather is a 1972 American epic crime film directed by Francis Ford Coppola, who co-wrote the screenplay with Mario Puzo based on Puzo's best-selling 1969 novel.",
            "Nino Rota was an Italian composer and pianist renowned for his film scores. He composed the soundtrack for Francis Ford Coppola's The Godfather (1972), including the iconic 'Love Theme from The Godfather'."
        ],
        "answer": "Nino Rota"
    },
    {
        "id": "hotpot_009",
        "question": "Who chaired the NASA committee that curated the contents of the Voyager Golden Record launched on Voyager 1?",
        "gold_passages": [
            "Voyager 1 is a space probe launched by NASA on September 5, 1977, as part of the Voyager program to study the outer Solar System and interstellar space.",
            "The Voyager Golden Records are two phonograph records that were included aboard both Voyager spacecraft. The committee that selected the images, natural sounds, languages, and music was chaired by American astronomer Carl Sagan."
        ],
        "answer": "Carl Sagan"
    },
    {
        "id": "hotpot_010",
        "question": "With which French physicist did Marie Curie and Pierre Curie share the 1903 Nobel Prize in Physics?",
        "gold_passages": [
            "Marie Curie and Pierre Curie conducted pioneering research on radioactivity, isolating polonium and radium from pitchblende in their Paris laboratory.",
            "The 1903 Nobel Prize in Physics was awarded jointly to Henri Becquerel 'in recognition of the extraordinary services he has rendered by his discovery of spontaneous radioactivity', and to Pierre Curie and Marie Curie 'in recognition of the extraordinary services they have rendered by their joint researches on the radiation phenomena'."
        ],
        "answer": "Henri Becquerel"
    },
    {
        "id": "hotpot_011",
        "question": "What is the name of the highest volcanic cone of Mount Kilimanjaro in Tanzania?",
        "gold_passages": [
            "Mount Kilimanjaro is a dormant stratovolcano in Tanzania and the highest mountain in Africa, rising approximately 5,895 metres above sea level.",
            "Kilimanjaro consists of three distinct volcanic cones: Kibo, Mawenzi, and Shira. Kibo is the highest cone and contains Uhuru Peak at 5,895 metres, the summit of the mountain."
        ],
        "answer": "Kibo"
    },
    {
        "id": "hotpot_012",
        "question": "Which mathematician introduced the concept of the 'bit' in his landmark 1948 paper 'A Mathematical Theory of Communication'?",
        "gold_passages": [
            "A Mathematical Theory of Communication is an influential 1948 paper published in the Bell System Technical Journal that founded the field of information theory.",
            "Claude Shannon was an American mathematician and electrical engineer known as the 'father of information theory'. In his 1948 paper, he credited John Tukey with coining the term 'bit' as a contraction of binary digit."
        ],
        "answer": "Claude Shannon"
    },
    {
        "id": "hotpot_013",
        "question": "Which French diplomat who led the Suez Canal construction headed the initial French project to excavate the Panama Canal?",
        "gold_passages": [
            "The Suez Canal is an artificial sea-level waterway in Egypt connecting the Mediterranean Sea to the Red Sea, officially opened in November 1869 under the leadership of French diplomat Ferdinand de Lesseps.",
            "The French construction attempt on the Panama Canal began in 1881 under Ferdinand de Lesseps's Panama Canal Company, but the venture collapsed due to engineering challenges and tropical diseases such as malaria and yellow fever."
        ],
        "answer": "Ferdinand de Lesseps"
    },
    {
        "id": "hotpot_014",
        "question": "Which Soviet aerospace engineer and chief designer directed the launch of Sputnik 1 in 1957?",
        "gold_passages": [
            "Sputnik 1 was the first artificial Earth satellite, launched into an elliptical low Earth orbit by the Soviet Union on October 4, 1957.",
            "Sergei Korolev was the lead Soviet rocket engineer and spacecraft designer during the Space Race between the United States and the Soviet Union, responsible for directing the Sputnik 1 mission and Yuri Gagarin's flight."
        ],
        "answer": "Sergei Korolev"
    },
    {
        "id": "hotpot_015",
        "question": "In which lunar mare did Apollo 11's Lunar Module Eagle touch down in July 1969?",
        "gold_passages": [
            "Apollo 11 was the American spaceflight that first landed humans on the Moon on July 20, 1969, carrying commander Neil Armstrong and lunar module pilot Buzz Aldrin.",
            "The Lunar Module Eagle landed in the southern part of Mare Tranquillitatis (the Sea of Tranquility), where Armstrong famously announced: 'Houston, Tranquility Base here. The Eagle has landed.'"
        ],
        "answer": "Sea of Tranquility"
    },
    {
        "id": "hotpot_016",
        "question": "Which chemist captured Photograph 51, providing critical evidence for the helical structure of DNA?",
        "gold_passages": [
            "Photograph 51 is the nickname given to an X-ray diffraction image of crystallized DNA taken in May 1952 at King's College London, which provided key clues to DNA's double-helix geometry.",
            "Rosalind Franklin was an English chemist and X-ray crystallographer whose work under John Randall at King's College London produced Photograph 51, captured with graduate student Raymond Gosling."
        ],
        "answer": "Rosalind Franklin"
    },
    {
        "id": "hotpot_017",
        "question": "Which Norwegian expressionist artist created the 1893 masterpiece The Scream?",
        "gold_passages": [
            "The Scream is the popular name given to a composition created by Norwegian artist Edvard Munch in 1893, showing an agonizing figure set against a turbulent orange sky.",
            "Edvard Munch (1863-1944) was a Norwegian painter and printmaker whose psychological themes heavily influenced German Expressionism in the early 20th century."
        ],
        "answer": "Edvard Munch"
    },
    {
        "id": "hotpot_018",
        "question": "Which American architect designed the Burj Khalifa in Dubai, the world's tallest building?",
        "gold_passages": [
            "The Burj Khalifa is a skyscraper in Dubai, United Arab Emirates, standing at a total height of 829.8 metres, making it the tallest building and structure in the world since its completion in 2009.",
            "Adrian Smith is an American architect who served as the consulting design partner at Skidmore, Owings & Merrill (SOM) where he designed the Burj Khalifa and the Jin Mao Tower."
        ],
        "answer": "Adrian Smith"
    },
    {
        "id": "hotpot_019",
        "question": "Which Irish modernist author wrote Ulysses, chronicling the experiences of Leopold Bloom on June 16, 1904?",
        "gold_passages": [
            "Ulysses is a modernist novel that chronicles the appointments and encounters of Leopold Bloom in Dublin in the course of an ordinary day, June 16, 1904.",
            "James Joyce (1882-1941) was an Irish novelist, short story writer, and poet who authored Dubliners, A Portrait of the Artist as a Young Man, Ulysses, and Finnegans Wake."
        ],
        "answer": "James Joyce"
    },
    {
        "id": "hotpot_020",
        "question": "At which English country estate did Allied cryptanalysts decrypt military messages generated by the Enigma machine?",
        "gold_passages": [
            "The Enigma machine was a cipher device developed and used in the early-to-mid 20th century to protect commercial, diplomatic, and military communication, utilized extensively by Nazi Germany during World War II.",
            "Bletchley Park is an English country house and estate in Milton Keynes, Buckinghamshire, that became the principal centre of Allied codebreaking during the Second World War."
        ],
        "answer": "Bletchley Park"
    },
    {
        "id": "hotpot_021",
        "question": "Which American author won the 1954 Nobel Prize in Literature following the publication of The Old Man and the Sea?",
        "gold_passages": [
            "The Old Man and the Sea is a 1952 novella written by American author Ernest Hemingway about an aging Cuban fisherman named Santiago who struggles with a giant marlin.",
            "Ernest Hemingway was an American novelist and short-story writer who received the Pulitzer Prize for Fiction in 1953 and the Nobel Prize in Literature in 1954 for his mastery of the art of modern narration."
        ],
        "answer": "Ernest Hemingway"
    },
    {
        "id": "hotpot_022",
        "question": "Which English computer scientist invented the World Wide Web in 1989 while employed at CERN?",
        "gold_passages": [
            "CERN (the European Organization for Nuclear Research) operates the largest particle physics laboratory in the world, located northwest of Geneva on the Franco-Swiss border.",
            "Tim Berners-Lee is an English computer scientist who invented the World Wide Web in 1989 while working as an independent contractor at CERN, developing HTML, HTTP, and the first web browser."
        ],
        "answer": "Tim Berners-Lee"
    },
    {
        "id": "hotpot_023",
        "question": "Which American author wrote the 1925 novel The Great Gatsby, set in fictional West Egg on Long Island?",
        "gold_passages": [
            "The Great Gatsby is a 1925 novel by American author F. Scott Fitzgerald following the interactions of narrator Nick Carraway with mysterious millionaire Jay Gatsby on Long Island.",
            "F. Scott Fitzgerald was an American novelist and essayist whose works illustrate the flamboyance and excess of the Jazz Age."
        ],
        "answer": "F. Scott Fitzgerald"
    },
    {
        "id": "hotpot_024",
        "question": "Which Scottish physician and bacteriologist discovered penicillin at St Mary's Hospital in London?",
        "gold_passages": [
            "Penicillin was discovered in September 1928 when an unwashed Petri dish containing Staphylococcus was found contaminated with a mould that inhibited bacterial growth.",
            "Alexander Fleming was a Scottish physician and microbiologist working at St Mary's Hospital Medical School in London when he observed the antibiotic properties of Penicillium notatum."
        ],
        "answer": "Alexander Fleming"
    },
    {
        "id": "hotpot_025",
        "question": "Which Mughal emperor commissioned the construction of the Taj Mahal in Agra as a tomb for his wife Mumtaz Mahal?",
        "gold_passages": [
            "The Taj Mahal is an ivory-white marble mausoleum on the south bank of the Yamuna river in the Indian city of Agra, housing the tomb of Mumtaz Mahal.",
            "Shah Jahan was the fifth Mughal emperor, reigning from 1628 to 1658. In 1632, he commissioned the Taj Mahal to commemorate his favorite wife Mumtaz Mahal, who died giving birth to their fourteenth child."
        ],
        "answer": "Shah Jahan"
    },
    {
        "id": "hotpot_026",
        "question": "For which American astronomer, who confirmed the existence of galaxies beyond the Milky Way, was the Hubble Space Telescope named?",
        "gold_passages": [
            "The Hubble Space Telescope was launched into low Earth orbit in 1990 by NASA with contributions from the European Space Agency.",
            "Edwin Hubble (1889-1953) was an American astronomer who proved that many previously observed nebulae were actually separate galaxies beyond the Milky Way and demonstrated cosmological redshift."
        ],
        "answer": "Edwin Hubble"
    },
    {
        "id": "hotpot_027",
        "question": "Which Finnish software engineer initiated development of the Linux kernel while studying at the University of Helsinki?",
        "gold_passages": [
            "The Linux kernel is a free and open-source, monolithic, modular, multitasking Unix-like operating system kernel created in 1991.",
            "Linus Torvalds is a Finnish-American software engineer who wrote the original Linux kernel while attending the University of Helsinki, releasing version 0.01 in September 1991."
        ],
        "answer": "Linus Torvalds"
    },
    {
        "id": "hotpot_028",
        "question": "In which French national museum in Paris is Leonardo da Vinci's Mona Lisa permanently displayed?",
        "gold_passages": [
            "The Mona Lisa is a half-length portrait painting by the Italian Renaissance artist Leonardo da Vinci, considered one of the most famous paintings in the world.",
            "The Louvre Museum is the national museum and art gallery of France, housed in the Louvre Palace in Paris, where the Mona Lisa has been on permanent display since 1797."
        ],
        "answer": "Louvre Museum"
    },
    {
        "id": "hotpot_029",
        "question": "Which computer scientist created the C programming language and co-developed the Unix operating system at Bell Labs?",
        "gold_passages": [
            "The C programming language was developed between 1969 and 1973 at Bell Labs to re-implement the Unix operating system in a portable high-level language.",
            "Dennis Ritchie was an American computer scientist who created C and, alongside Ken Thompson and others, developed Unix, receiving the Turing Award in 1983."
        ],
        "answer": "Dennis Ritchie"
    },
    {
        "id": "hotpot_030",
        "question": "Who served as the chief engineer in charge of constructing the Golden Gate Bridge in San Francisco?",
        "gold_passages": [
            "The Golden Gate Bridge is a suspension bridge spanning the Golden Gate strait between San Francisco and Marin County, California, opened in 1937.",
            "Joseph Strauss was an American engineer who served as the chief engineer for the Golden Gate Bridge project, overseeing its design and construction through completion."
        ],
        "answer": "Joseph Strauss"
    },
    {
        "id": "hotpot_031",
        "question": "Which German mathematician and astronomer compiled the Rudolphine Tables using Tycho Brahe's planetary observations?",
        "gold_passages": [
            "The Rudolphine Tables consist of a star catalogue and planetary tables published in 1627, dedicated to the Holy Roman Emperor Rudolf II.",
            "Johannes Kepler was a German astronomer, mathematician, and astrologer best known for his laws of planetary motion, who used Tycho Brahe's extensive observational records to complete the Rudolphine Tables."
        ],
        "answer": "Johannes Kepler"
    },
    {
        "id": "hotpot_032",
        "question": "Which Dutch programmer conceived the Python programming language while working at CWI in Amsterdam?",
        "gold_passages": [
            "Python is a high-level, general-purpose programming language whose design philosophy emphasizes code readability with the use of significant indentation.",
            "Guido van Rossum is a Dutch programmer who created Python in the late 1980s at Centrum Wiskunde & Informatica (CWI) as a successor to the ABC programming language."
        ],
        "answer": "Guido van Rossum"
    },
    {
        "id": "hotpot_033",
        "question": "Which Renaissance master was commissioned by Pope Julius II to paint the ceiling of the Sistine Chapel?",
        "gold_passages": [
            "The Sistine Chapel ceiling was painted between 1508 and 1512 in the Vatican under commission from Pope Julius II, featuring scenes from the Book of Genesis.",
            "Michelangelo Buonarroti was an Italian sculptor, painter, architect, and poet of the High Renaissance whose fresco cycle on the Sistine Chapel ceiling is regarded as a crowning achievement of Western art."
        ],
        "answer": "Michelangelo"
    },
    {
        "id": "hotpot_034",
        "question": "Which Russian chemist formulated the Periodic Law and organized the elements into the first periodic table in 1869?",
        "gold_passages": [
            "The periodic table is a tabular display of chemical elements organized by atomic number, electron configuration, and recurring chemical properties.",
            "Dmitri Mendeleev was a Russian chemist and inventor who formulated the Periodic Law in 1869, predicting the discovery and properties of then-unknown elements such as gallium and germanium."
        ],
        "answer": "Dmitri Mendeleev"
    },
    {
        "id": "hotpot_035",
        "question": "Which European heavy-lift rocket launched the James Webb Space Telescope from French Guiana in December 2021?",
        "gold_passages": [
            "The James Webb Space Telescope (JWST) is an infrared space observatory launched on December 25, 2021, stationed at the Sun-Earth L2 Lagrange point.",
            "Ariane 5 was a European heavy-lift launch vehicle operated by Arianespace that successfully deployed the James Webb Space Telescope from the Guiana Space Centre in Kourou, French Guiana."
        ],
        "answer": "Ariane 5"
    },
    {
        "id": "hotpot_036",
        "question": "Which English author wrote Pride and Prejudice, introducing the characters Elizabeth Bennet and Fitzwilliam Darcy?",
        "gold_passages": [
            "Pride and Prejudice is an 1813 romantic novel that follows the turbulent relationship between Elizabeth Bennet, the daughter of a country gentleman, and Fitzwilliam Darcy, a wealthy aristocratic landowner.",
            "Jane Austen (1775-1817) was an English novelist known primarily for her six major novels interpreting and critiquing the British landed gentry at the end of the 18th century, including Sense and Sensibility and Pride and Prejudice."
        ],
        "answer": "Jane Austen"
    },
    {
        "id": "hotpot_037",
        "question": "Which Danish architect designed the Sydney Opera House after winning an international competition in 1957?",
        "gold_passages": [
            "The Sydney Opera House is a multi-venue performing arts centre at Sydney Harbour in New South Wales, Australia, famous for its distinctive shell-shaped vaulted roofs.",
            "Jørn Utzon was a Danish architect who won the international design competition for the Sydney Opera House in 1957 and was awarded the Pritzker Architecture Prize in 2003 for the building."
        ],
        "answer": "Jørn Utzon"
    },
    {
        "id": "hotpot_038",
        "question": "Which theoretical physicist published the paper on Brownian motion and the special theory of relativity during his 1905 Annus Mirabilis?",
        "gold_passages": [
            "The Annus Mirabilis papers are four papers published in the Annalen der Physik scientific journal in 1905, establishing foundational principles in modern physics.",
            "Albert Einstein was a German-born theoretical physicist who published these four groundbreaking articles in 1905, covering the photoelectric effect, Brownian motion, special relativity, and mass-energy equivalence."
        ],
        "answer": "Albert Einstein"
    },
    {
        "id": "hotpot_039",
        "question": "Who authored the 1990 science fiction novel Jurassic Park, which Steven Spielberg adapted into a 1993 film?",
        "gold_passages": [
            "Jurassic Park is a 1993 American science fiction adventure film directed by Steven Spielberg and produced by Kathleen Kennedy and Gerald R. Molen.",
            "Michael Crichton was an American author and filmmaker who wrote the 1990 techno-thriller novel Jurassic Park, which explores genetic cloning and chaos theory on Isla Nublar."
        ],
        "answer": "Michael Crichton"
    },
    {
        "id": "hotpot_040",
        "question": "Which reigning World Chess Champion lost a famous six-game match to the IBM supercomputer Deep Blue in 1997?",
        "gold_passages": [
            "Deep Blue was a chess-playing supercomputer developed by IBM that became the first computer system to defeat a reigning world chess champion in a standard match under tournament time controls.",
            "Garry Kasparov held the World Chess Championship from 1985 to 2000 and played against Deep Blue in May 1997 in New York City, losing the six-game match with two losses, three draws, and one win."
        ],
        "answer": "Garry Kasparov"
    },
    {
        "id": "hotpot_041",
        "question": "Which ancient Athenian sculptor created the colossal chryselephantine statue of Athena Parthenos inside the Parthenon?",
        "gold_passages": [
            "The Parthenon is a former temple on the Athenian Acropolis, Greece, dedicated to the goddess Athena during the height of the Delian League in the 5th century BC.",
            "Phidias was a Greek sculptor, painter, and architect who directed the construction of the Parthenon's sculptures and crafted the massive chryselephantine statue of Athena Parthenos."
        ],
        "answer": "Phidias"
    },
    {
        "id": "hotpot_042",
        "question": "Which English naturalist formulated the theory of evolution by natural selection after his voyage on HMS Beagle?",
        "gold_passages": [
            "HMS Beagle was a Cherokee-class 10-gun brig-sloop of the Royal Navy that conducted a second survey voyage from 1831 to 1836, surveying the coasts of South America and the Galápagos Islands.",
            "Charles Darwin was an English naturalist, geologist, and biologist whose observations on flora, fauna, and fossils during the HMS Beagle expedition formed the basis of his 1859 book On the Origin of Species."
        ],
        "answer": "Charles Darwin"
    },
    {
        "id": "hotpot_043",
        "question": "Which Spanish artist created the anti-war masterpiece Guernica in response to the 1937 bombing of a Basque town?",
        "gold_passages": [
            "Guernica is a large 1937 oil painting on canvas that depicts the suffering wrought by violence and chaos during the aerial bombing of Guernica in northern Spain by Nazi German and Fascist Italian warplanes.",
            "Pablo Picasso was a Spanish painter and sculptor regarded as one of the most influential artists of the 20th century, who painted Guernica for the Spanish Pavilion at the 1937 Paris International Exposition."
        ],
        "answer": "Pablo Picasso"
    },
    {
        "id": "hotpot_044",
        "question": "Which rocket engineer led the Marshall Space Flight Center team that designed the Saturn V rocket for the Apollo program?",
        "gold_passages": [
            "The Saturn V was an American human-rated super heavy-lift launch vehicle used by NASA between 1967 and 1973 for the Apollo lunar landing missions and to launch Skylab.",
            "Wernher von Braun was an aerospace engineer and space architect who directed the development of the Saturn V rocket while serving as director of NASA's Marshall Space Flight Center in Huntsville, Alabama."
        ],
        "answer": "Wernher von Braun"
    },
    {
        "id": "hotpot_045",
        "question": "Which marine biologist wrote the 1962 book Silent Spring, exposing the environmental dangers of synthetic pesticides?",
        "gold_passages": [
            "Silent Spring is an environmental science book published in September 1962 documenting the adverse environmental effects caused by the indiscriminate use of pesticides, particularly DDT.",
            "Rachel Carson was an American marine biologist, writer, and conservationist whose book Silent Spring sparked the modern global environmental movement and led to the creation of the U.S. Environmental Protection Agency."
        ],
        "answer": "Rachel Carson"
    },
    {
        "id": "hotpot_046",
        "question": "What is the name of the first module launched into orbit for the International Space Station in November 1998?",
        "gold_passages": [
            "The International Space Station (ISS) is a modular space station in low Earth orbit, established as a joint project involving NASA, Roscosmos, JAXA, ESA, and CSA.",
            "Zarya, also known as the Functional Cargo Block (FGB), was the first module of the ISS to be launched into orbit, lifted by a Russian Proton rocket from Baikonur Cosmodrome on November 20, 1998."
        ],
        "answer": "Zarya"
    },
    {
        "id": "hotpot_047",
        "question": "Which Colombian Nobel laureate wrote One Hundred Years of Solitude, chronicling the Buendía family in Macondo?",
        "gold_passages": [
            "One Hundred Years of Solitude is a 1967 landmark novel that tells the multi-generational story of the Buendía family, whose patriarch founded the town of Macondo in Colombia.",
            "Gabriel García Márquez was a Colombian novelist, short-story writer, and journalist who received the Nobel Prize in Literature in 1982 and popularized the magical realism literary style."
        ],
        "answer": "Gabriel García Márquez"
    },
    {
        "id": "hotpot_048",
        "question": "In which particle collider operated by CERN was the Higgs boson detected by the ATLAS and CMS experiments in 2012?",
        "gold_passages": [
            "The Higgs boson is an elementary particle in the Standard Model of particle physics, discovered through decay signatures confirmed in July 2012 by ATLAS and CMS collaborations.",
            "The Large Hadron Collider (LHC) is the world's largest and highest-energy particle collider, built by CERN in a 27-kilometre underground tunnel beneath the France-Switzerland border."
        ],
        "answer": "Large Hadron Collider"
    },
    {
        "id": "hotpot_049",
        "question": "Which American sculptor is famous for inventing the mobile, an art form composed of suspended balanced elements moving in the air?",
        "gold_passages": [
            "A mobile is a type of kinetic sculpture constructed to take advantage of the principle of equilibrium, consisting of delicate balanced rods and shapes that rotate with ambient air currents.",
            "Alexander Calder was an American sculptor recognized for his innovative wire sculptures and mobiles, as well as monumental static sculptures known as stabiles."
        ],
        "answer": "Alexander Calder"
    },
    {
        "id": "hotpot_050",
        "question": "Which English author wrote Frankenstein; or, The Modern Prometheus during a summer stay near Lake Geneva in 1816?",
        "gold_passages": [
            "Frankenstein; or, The Modern Prometheus is an 1818 Gothic novel recounting the story of scientist Victor Frankenstein, who creates a sapient creature in an unorthodox scientific experiment.",
            "Mary Shelley was an English novelist who conceived and drafted Frankenstein in the summer of 1816 at the Villa Diodati near Lake Geneva, Switzerland, alongside Percy Bysshe Shelley and Lord Byron."
        ],
        "answer": "Mary Shelley"
    }
]

# ---------------------------------------------------------
# 2. LongMemEval Sample (50 items across 5 abilities)
# ---------------------------------------------------------
# Distribution:
# - information_extraction: 12 (lme_001 to lme_012)
# - knowledge_updates: 10 (lme_013 to lme_022)
# - temporal_reasoning: 10 (lme_023 to lme_032)
# - multi_session_reasoning: 10 (lme_033 to lme_042)
# - abstention: 8 (lme_043 to lme_050)
longmemeval_data = [
    # 1. Information Extraction (12 items)
    {
        "id": "lme_001",
        "ability": "information_extraction",
        "question": "What is Alice Vance's favorite morning hot beverage?",
        "subject": "Alice Vance",
        "gold_answer": "Earl Grey tea",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Alice Vance",
                "relation": "prefers_beverage",
                "fact": "Alice Vance drinks loose-leaf Earl Grey tea every morning with a dash of bergamot.",
                "object": "Earl Grey tea"
            }
        ]
    },
    {
        "id": "lme_002",
        "ability": "information_extraction",
        "question": "What primary programming language does David Kim use for systems development?",
        "subject": "David Kim",
        "gold_answer": "Rust",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "David Kim",
                "relation": "codes_in",
                "fact": "David Kim specializes in high-throughput network daemons written in Rust.",
                "object": "Rust"
            }
        ]
    },
    {
        "id": "lme_003",
        "ability": "information_extraction",
        "question": "What breed of dog does Elena Rostova own?",
        "subject": "Elena Rostova",
        "gold_answer": "Golden Retriever",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Elena Rostova",
                "relation": "owns_pet",
                "fact": "Elena Rostova lives with her three-year-old Golden Retriever named Apollo.",
                "object": "Golden Retriever"
            }
        ]
    },
    {
        "id": "lme_004",
        "ability": "information_extraction",
        "question": "In which city does Marcus Chen maintain his primary residence?",
        "subject": "Marcus Chen",
        "gold_answer": "Seattle",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Marcus Chen",
                "relation": "resides_in",
                "fact": "Marcus Chen lives in a loft apartment in the Capitol Hill neighborhood of Seattle.",
                "object": "Seattle"
            }
        ]
    },
    {
        "id": "lme_005",
        "ability": "information_extraction",
        "question": "What specific electric guitar model does Sarah Connor play?",
        "subject": "Sarah Connor",
        "gold_answer": "Fender Stratocaster",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sarah Connor",
                "relation": "plays_instrument",
                "fact": "Sarah Connor plays an American Professional II Fender Stratocaster in sunburst finish.",
                "object": "Fender Stratocaster"
            }
        ]
    },
    {
        "id": "lme_006",
        "ability": "information_extraction",
        "question": "Which key switches does Julian Weber use in his custom mechanical keyboard?",
        "subject": "Julian Weber",
        "gold_answer": "Cherry MX Brown",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Julian Weber",
                "relation": "uses_hardware",
                "fact": "Julian Weber built an 80% custom mechanical keyboard equipped with tactile Cherry MX Brown switches.",
                "object": "Cherry MX Brown"
            }
        ]
    },
    {
        "id": "lme_007",
        "ability": "information_extraction",
        "question": "At which institution did Priya Patel complete her doctorate degree?",
        "subject": "Priya Patel",
        "gold_answer": "Stanford University",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Priya Patel",
                "relation": "graduated_from",
                "fact": "Priya Patel earned her PhD in Computer Science from Stanford University.",
                "object": "Stanford University"
            }
        ]
    },
    {
        "id": "lme_008",
        "ability": "information_extraction",
        "question": "Who is Carlos Mendez's favorite fiction author?",
        "subject": "Carlos Mendez",
        "gold_answer": "Jorge Luis Borges",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Carlos Mendez",
                "relation": "favorite_author",
                "fact": "Carlos Mendez's favorite author is Argentine fabulist Jorge Luis Borges.",
                "object": "Jorge Luis Borges"
            }
        ]
    },
    {
        "id": "lme_009",
        "ability": "information_extraction",
        "question": "What model of sports car does Hana Takahashi drive?",
        "subject": "Hana Takahashi",
        "gold_answer": "Mazda MX-5 Miata",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Hana Takahashi",
                "relation": "drives_vehicle",
                "fact": "Hana Takahashi drives a red 2021 Mazda MX-5 Miata convertible.",
                "object": "Mazda MX-5 Miata"
            }
        ]
    },
    {
        "id": "lme_010",
        "ability": "information_extraction",
        "question": "Which athletic segment does Liam O'Connor consider his weakest in triathlon competitions?",
        "subject": "Liam O'Connor",
        "gold_answer": "swimming",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Liam O'Connor",
                "relation": "training_focus",
                "fact": "Liam O'Connor considers open-water swimming to be his weakest discipline compared to cycling and running.",
                "object": "swimming"
            }
        ]
    },
    {
        "id": "lme_011",
        "ability": "information_extraction",
        "question": "What model of home espresso machine did Sophia Dubois purchase?",
        "subject": "Sophia Dubois",
        "gold_answer": "La Marzocco Micra",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sophia Dubois",
                "relation": "owns_appliance",
                "fact": "Sophia Dubois pulled morning espresso shots on her newly installed La Marzocco Micra.",
                "object": "La Marzocco Micra"
            }
        ]
    },
    {
        "id": "lme_012",
        "ability": "information_extraction",
        "question": "What is the title of the weekly audio podcast hosted by Benjamin Thorne?",
        "subject": "Benjamin Thorne",
        "gold_answer": "The Distributed Ledger",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Benjamin Thorne",
                "relation": "produces_podcast",
                "fact": "Benjamin Thorne hosts a technical weekly podcast titled The Distributed Ledger.",
                "object": "The Distributed Ledger"
            }
        ]
    },

    # 2. Knowledge Updates (10 items)
    {
        "id": "lme_013",
        "ability": "knowledge_updates",
        "question": "What is Alice Vance's current job role?",
        "subject": "Alice Vance",
        "gold_answer": "Engineering Manager",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Alice Vance",
                "relation": "held_role",
                "fact": "In January 2023, Alice Vance worked as a Senior Software Engineer on the platform team.",
                "object": "Senior Software Engineer"
            },
            {
                "subject": "Alice Vance",
                "relation": "promoted_to",
                "fact": "In February 2024, Alice Vance was formally promoted to Engineering Manager overseeing infrastructure.",
                "object": "Engineering Manager"
            }
        ]
    },
    {
        "id": "lme_014",
        "ability": "knowledge_updates",
        "question": "In which city does Marcus Chen presently live after his recent relocation?",
        "subject": "Marcus Chen",
        "gold_answer": "Zurich",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Marcus Chen",
                "relation": "lived_in",
                "fact": "Prior to summer 2024, Marcus Chen was a resident of Seattle, Washington.",
                "object": "Seattle"
            },
            {
                "subject": "Marcus Chen",
                "relation": "relocated_to",
                "fact": "In August 2024, Marcus Chen relocated permanently to Zurich, Switzerland for a new laboratory role.",
                "object": "Zurich"
            }
        ]
    },
    {
        "id": "lme_015",
        "ability": "knowledge_updates",
        "question": "What code editor does David Kim currently use as his default development environment?",
        "subject": "David Kim",
        "gold_answer": "Neovim",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "David Kim",
                "relation": "previously_used",
                "fact": "Throughout 2022, David Kim used Visual Studio Code as his primary editor.",
                "object": "Visual Studio Code"
            },
            {
                "subject": "David Kim",
                "relation": "switched_to",
                "fact": "In mid-2023, David Kim transitioned entirely to Neovim with Lua configs as his default development environment.",
                "object": "Neovim"
            }
        ]
    },
    {
        "id": "lme_016",
        "ability": "knowledge_updates",
        "question": "What car does Elena Rostova currently drive following her vehicle replacement?",
        "subject": "Elena Rostova",
        "gold_answer": "Tesla Model Y",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Elena Rostova",
                "relation": "previously_owned",
                "fact": "Elena Rostova previously drove a silver 2016 Honda Civic.",
                "object": "Honda Civic"
            },
            {
                "subject": "Elena Rostova",
                "relation": "currently_drives",
                "fact": "In November 2023, Elena sold her Honda and bought a Tesla Model Y electric crossover.",
                "object": "Tesla Model Y"
            }
        ]
    },
    {
        "id": "lme_017",
        "ability": "knowledge_updates",
        "question": "Which company does Priya Patel currently work for?",
        "subject": "Priya Patel",
        "gold_answer": "Anthropic",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Priya Patel",
                "relation": "former_employer",
                "fact": "Priya Patel worked as a Research Scientist at Google DeepMind until early 2024.",
                "object": "Google DeepMind"
            },
            {
                "subject": "Priya Patel",
                "relation": "current_employer",
                "fact": "In March 2024, Priya Patel joined Anthropic as a Member of Technical Staff on the alignment team.",
                "object": "Anthropic"
            }
        ]
    },
    {
        "id": "lme_018",
        "ability": "knowledge_updates",
        "question": "What dietary regimen does Julian Weber follow today?",
        "subject": "Julian Weber",
        "gold_answer": "vegan",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Julian Weber",
                "relation": "former_diet",
                "fact": "Julian Weber consumed an omnivorous diet through the end of 2022.",
                "object": "omnivore"
            },
            {
                "subject": "Julian Weber",
                "relation": "current_diet",
                "fact": "On January 1, 2023, Julian Weber adopted a strict vegan lifestyle for ethical reasons and maintains it today.",
                "object": "vegan"
            }
        ]
    },
    {
        "id": "lme_019",
        "ability": "knowledge_updates",
        "question": "What operating system is installed on Sarah Connor's primary workstation?",
        "subject": "Sarah Connor",
        "gold_answer": "NixOS",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sarah Connor",
                "relation": "former_os",
                "fact": "Sarah Connor ran macOS on an Apple Silicon MacBook Pro during 2022.",
                "object": "macOS"
            },
            {
                "subject": "Sarah Connor",
                "relation": "current_os",
                "fact": "In October 2023, Sarah Connor switched her primary workstation to a reproducible NixOS setup on a ThinkPad P1.",
                "object": "NixOS"
            }
        ]
    },
    {
        "id": "lme_020",
        "ability": "knowledge_updates",
        "question": "Which public cloud provider does Benjamin Thorne now deploy his startup's production services on?",
        "subject": "Benjamin Thorne",
        "gold_answer": "GCP",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Benjamin Thorne",
                "relation": "former_cloud",
                "fact": "Benjamin Thorne initially hosted all production workloads on Amazon Web Services (AWS) using EKS.",
                "object": "AWS"
            },
            {
                "subject": "Benjamin Thorne",
                "relation": "current_cloud",
                "fact": "In spring 2024, Benjamin Thorne completed a total migration from AWS to Google Cloud Platform (GCP) for GKE Autopilot.",
                "object": "GCP"
            }
        ]
    },
    {
        "id": "lme_021",
        "ability": "knowledge_updates",
        "question": "In which Paris neighborhood is Sophia Dubois's current studio apartment located?",
        "subject": "Sophia Dubois",
        "gold_answer": "Montmartre",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sophia Dubois",
                "relation": "past_residence",
                "fact": "Sophia Dubois rented a fourth-floor apartment in Belleville until late 2023.",
                "object": "Belleville"
            },
            {
                "subject": "Sophia Dubois",
                "relation": "current_residence",
                "fact": "In January 2024, Sophia signed a lease and moved into an atelier in Montmartre overlooking the Sacré-Cœur.",
                "object": "Montmartre"
            }
        ]
    },
    {
        "id": "lme_022",
        "ability": "knowledge_updates",
        "question": "What is Carlos Mendez's current leadership role on the engineering team?",
        "subject": "Carlos Mendez",
        "gold_answer": "Tech Lead",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Carlos Mendez",
                "relation": "past_role",
                "fact": "Carlos Mendez contributed as an Individual Contributor Backend Developer during 2023.",
                "object": "Backend Developer"
            },
            {
                "subject": "Carlos Mendez",
                "relation": "current_role",
                "fact": "Starting June 2024, Carlos Mendez took on the responsibilities of Tech Lead for the Core Payments cluster.",
                "object": "Tech Lead"
            }
        ]
    },

    # 3. Temporal Reasoning (10 items)
    {
        "id": "lme_023",
        "ability": "temporal_reasoning",
        "question": "Which legacy system was Alice Vance maintaining immediately prior to the Q3 2023 migration?",
        "subject": "Alice Vance",
        "gold_answer": "Legacy Billing Service",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Alice Vance",
                "relation": "worked_on",
                "fact": "Between January 2022 and June 2023, Alice Vance maintained the monolithic Legacy Billing Service.",
                "object": "Legacy Billing Service"
            },
            {
                "subject": "Alice Vance",
                "relation": "migrated_to",
                "fact": "In July 2023 (Q3), Alice Vance led the migration off the billing monolith to EventStream Engine.",
                "object": "EventStream Engine"
            }
        ]
    },
    {
        "id": "lme_024",
        "ability": "temporal_reasoning",
        "question": "How many total years did David Kim spend working at Stripe before his departure?",
        "subject": "David Kim",
        "gold_answer": "4 years",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "David Kim",
                "relation": "joined_company",
                "fact": "David Kim started his tenure at Stripe in February 2018.",
                "object": "February 2018"
            },
            {
                "subject": "David Kim",
                "relation": "departed_company",
                "fact": "David Kim concluded his final engineering sprint at Stripe in February 2022 after four full years.",
                "object": "February 2022"
            }
        ]
    },
    {
        "id": "lme_025",
        "ability": "temporal_reasoning",
        "question": "What companion did Elena Rostova adopt in May 2021?",
        "subject": "Elena Rostova",
        "gold_answer": "a Golden Retriever named Apollo",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Elena Rostova",
                "relation": "adopted",
                "fact": "On May 14, 2021, Elena Rostova adopted an eight-week-old Golden Retriever named Apollo from a local shelter.",
                "object": "a Golden Retriever named Apollo"
            }
        ]
    },
    {
        "id": "lme_026",
        "ability": "temporal_reasoning",
        "question": "Which Japanese city did Marcus Chen travel to immediately after completing his stay in Tokyo during October 2023?",
        "subject": "Marcus Chen",
        "gold_answer": "Kyoto",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Marcus Chen",
                "relation": "visited",
                "fact": "Marcus Chen stayed in Tokyo from October 1 to October 8, 2023.",
                "object": "Tokyo"
            },
            {
                "subject": "Marcus Chen",
                "relation": "traveled_next_to",
                "fact": "On October 9, 2023, Marcus took the Shinkansen directly from Tokyo to Kyoto, staying there for the subsequent week.",
                "object": "Kyoto"
            }
        ]
    },
    {
        "id": "lme_027",
        "ability": "temporal_reasoning",
        "question": "What fellowship did Priya Patel receive during the third year of her doctoral program in 2019?",
        "subject": "Priya Patel",
        "gold_answer": "NSF Graduate Research Fellowship",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Priya Patel",
                "relation": "began_phd",
                "fact": "Priya Patel entered Stanford's graduate program in September 2017.",
                "object": "September 2017"
            },
            {
                "subject": "Priya Patel",
                "relation": "awarded_fellowship",
                "fact": "In autumn 2019, during her third year of doctoral study, Priya was awarded the NSF Graduate Research Fellowship.",
                "object": "NSF Graduate Research Fellowship"
            }
        ]
    },
    {
        "id": "lme_028",
        "ability": "temporal_reasoning",
        "question": "Which major marathon did Julian Weber complete in autumn 2022?",
        "subject": "Julian Weber",
        "gold_answer": "Berlin Marathon",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Julian Weber",
                "relation": "ran_marathon",
                "fact": "In September 2022, Julian Weber traveled to Germany and completed the Berlin Marathon in 3 hours 18 minutes.",
                "object": "Berlin Marathon"
            }
        ]
    },
    {
        "id": "lme_029",
        "ability": "temporal_reasoning",
        "question": "Which open-source async library did Sarah Connor publish in June 2020 before founding Kernel Corp?",
        "subject": "Sarah Connor",
        "gold_answer": "FastAsyncIO",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sarah Connor",
                "relation": "released_library",
                "fact": "In June 2020, Sarah Connor published the initial 1.0 release of FastAsyncIO on GitHub.",
                "object": "FastAsyncIO"
            },
            {
                "subject": "Sarah Connor",
                "relation": "founded_company",
                "fact": "In November 2020, Sarah Connor co-founded Kernel Corp after the rapid adoption of FastAsyncIO.",
                "object": "Kernel Corp"
            }
        ]
    },
    {
        "id": "lme_030",
        "ability": "temporal_reasoning",
        "question": "What professional cloud certification did Carlos Mendez achieve in November 2021?",
        "subject": "Carlos Mendez",
        "gold_answer": "AWS Solutions Architect Professional",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Carlos Mendez",
                "relation": "earned_credential",
                "fact": "On November 18, 2021, Carlos Mendez passed the examination for AWS Solutions Architect Professional.",
                "object": "AWS Solutions Architect Professional"
            }
        ]
    },
    {
        "id": "lme_031",
        "ability": "temporal_reasoning",
        "question": "What was the title of the Paris gallery solo exhibition held by Sophia Dubois in September 2022?",
        "subject": "Sophia Dubois",
        "gold_answer": "L'Ombre et La Lumiere",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sophia Dubois",
                "relation": "exhibited_artwork",
                "fact": "Throughout September 2022, Sophia Dubois exhibited her charcoal series titled L'Ombre et La Lumiere in the Marais.",
                "object": "L'Ombre et La Lumiere"
            }
        ]
    },
    {
        "id": "lme_032",
        "ability": "temporal_reasoning",
        "question": "What was the topic of Benjamin Thorne's keynote talk at RustConf in August 2023?",
        "subject": "Benjamin Thorne",
        "gold_answer": "Zero-Cost Async Graphs",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Benjamin Thorne",
                "relation": "delivered_keynote",
                "fact": "At RustConf in August 2023, Benjamin Thorne gave the opening keynote entitled 'Zero-Cost Async Graphs'.",
                "object": "Zero-Cost Async Graphs"
            }
        ]
    },

    # 4. Multi-Session Reasoning (10 items)
    {
        "id": "lme_033",
        "ability": "multi_session_reasoning",
        "question": "When Alice Vance orders pasta dishes for group dinners, why must they be prepared without wheat?",
        "subject": "Alice Vance",
        "gold_answer": "She has celiac disease",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Alice Vance",
                "relation": "medical_condition",
                "fact": "[Session 1]: Alice Vance disclosed that she was clinically diagnosed with celiac disease and strictly avoids gluten.",
                "object": "celiac disease"
            },
            {
                "subject": "Alice Vance",
                "relation": "dinner_preference",
                "fact": "[Session 2]: Alice organized a team Italian dinner and requested special gluten-free penne for herself.",
                "object": "gluten-free pasta"
            }
        ]
    },
    {
        "id": "lme_034",
        "ability": "multi_session_reasoning",
        "question": "What mount system must a new prime lens support to be compatible with David Kim's primary camera body?",
        "subject": "David Kim",
        "gold_answer": "Sony E-mount",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "David Kim",
                "relation": "owns_camera",
                "fact": "[Session 1]: David Kim uses a Sony A7 IV full-frame mirrorless camera body for his street photography.",
                "object": "Sony A7 IV"
            },
            {
                "subject": "David Kim",
                "relation": "plans_purchase",
                "fact": "[Session 2]: David Kim asked for prime lens recommendations with fast aperture that fit his existing camera mount.",
                "object": "Sony E-mount prime lens"
            }
        ]
    },
    {
        "id": "lme_035",
        "ability": "multi_session_reasoning",
        "question": "Why does Elena Rostova require specific low-phosphorus prescription food for her pet cat Mochi?",
        "subject": "Elena Rostova",
        "gold_answer": "Mochi has chronic kidney disease",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Elena Rostova",
                "relation": "pet_diagnosis",
                "fact": "[Session 1]: Elena shared that her elderly rescue cat Mochi was diagnosed with early stage chronic kidney disease.",
                "object": "chronic kidney disease"
            },
            {
                "subject": "Elena Rostova",
                "relation": "purchased_diet",
                "fact": "[Session 2]: Elena asked the vet assistant to refill Mochi's wet food order with low-phosphorus renal support pate.",
                "object": "low-phosphorus renal food"
            }
        ]
    },
    {
        "id": "lme_036",
        "ability": "multi_session_reasoning",
        "question": "What maximum power wattage constraint must Marcus Chen's portable laptop charger satisfy to match his minimalist travel kit?",
        "subject": "Marcus Chen",
        "gold_answer": "45W",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Marcus Chen",
                "relation": "travel_kit",
                "fact": "[Session 1]: Marcus Chen packs only a single ultralight 45-watt GaN USB-C wall charger when traveling internationally.",
                "object": "45W GaN charger"
            },
            {
                "subject": "Marcus Chen",
                "relation": "laptop_shopping",
                "fact": "[Session 2]: Marcus seeks an ultrabook that can reliably charge at full speed without exceeding his 45W travel adapter limit.",
                "object": "45W USB-PD charging"
            }
        ]
    },
    {
        "id": "lme_037",
        "ability": "multi_session_reasoning",
        "question": "Why did Priya Patel consult a travel clinic physician for an acetazolamide prescription before her upcoming vacation?",
        "subject": "Priya Patel",
        "gold_answer": "She is embarking on a high-altitude trek in the Andes",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Priya Patel",
                "relation": "planned_trip",
                "fact": "[Session 1]: Priya booked an eight-day trekking expedition along the Salkantay trail in the Peruvian Andes reaching 4,600m.",
                "object": "high-altitude Peruvian Andes trek"
            },
            {
                "subject": "Priya Patel",
                "relation": "medical_prep",
                "fact": "[Session 2]: Priya picked up a preventive prescription of acetazolamide (Diamox) from her physician to combat acute mountain sickness.",
                "object": "acetazolamide prescription"
            }
        ]
    },
    {
        "id": "lme_038",
        "ability": "multi_session_reasoning",
        "question": "Why does Julian Weber use an ergonomic vertical mouse rather than a standard flat optical mouse?",
        "subject": "Julian Weber",
        "gold_answer": "He suffers from a repetitive strain injury (RSI) in his right wrist",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Julian Weber",
                "relation": "injury_history",
                "fact": "[Session 1]: Julian experienced sharp repetitive strain injury (RSI) symptoms in his right wrist tendon during coding marathons.",
                "object": "right wrist RSI"
            },
            {
                "subject": "Julian Weber",
                "relation": "ergonomic_hardware",
                "fact": "[Session 2]: On physical therapist advice, Julian replaced his flat optical gaming mouse with an angled ergonomic vertical mouse.",
                "object": "ergonomic vertical mouse"
            }
        ]
    },
    {
        "id": "lme_039",
        "ability": "multi_session_reasoning",
        "question": "What motorcycle model does Sarah Connor order maintenance parts for during her seasonal tune-up?",
        "subject": "Sarah Connor",
        "gold_answer": "2019 Triumph Bonneville T120",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sarah Connor",
                "relation": "owns_vehicle",
                "fact": "[Session 1]: Sarah Connor's garage houses a jet-black 2019 Triumph Bonneville T120 motorcycle.",
                "object": "2019 Triumph Bonneville T120"
            },
            {
                "subject": "Sarah Connor",
                "relation": "part_order",
                "fact": "[Session 2]: Sarah placed an online order for an OEM oil filter and crush washer matched specifically for her Bonneville.",
                "object": "Triumph motorcycle parts"
            }
        ]
    },
    {
        "id": "lme_040",
        "ability": "multi_session_reasoning",
        "question": "Why does Carlos Mendez ask baristas for oat milk in his cortados instead of dairy whole milk?",
        "subject": "Carlos Mendez",
        "gold_answer": "He is lactose intolerant",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Carlos Mendez",
                "relation": "dietary_restriction",
                "fact": "[Session 1]: Carlos Mendez mentioned having significant lactose intolerance since his college years.",
                "object": "lactose intolerance"
            },
            {
                "subject": "Carlos Mendez",
                "relation": "beverage_order",
                "fact": "[Session 2]: Carlos ordered his morning double-shot cortado explicitly crafted with steamed oat milk.",
                "object": "oat milk cortado"
            }
        ]
    },
    {
        "id": "lme_041",
        "ability": "multi_session_reasoning",
        "question": "Why does Sophia Dubois require heavy winter coats to feature smooth synthetic linings rather than wool?",
        "subject": "Sophia Dubois",
        "gold_answer": "She is allergic to wool",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Sophia Dubois",
                "relation": "contact_allergy",
                "fact": "[Session 1]: Sophia Dubois breaks out into contact dermatitis if untreated wool fibers touch her neck or wrists.",
                "object": "wool contact allergy"
            },
            {
                "subject": "Sophia Dubois",
                "relation": "wardrobe_criteria",
                "fact": "[Session 2]: Sophia vetted winter trench coats to guarantee the collars and interior cuffs had 100% cupro or fleece linings.",
                "object": "synthetic lining"
            }
        ]
    },
    {
        "id": "lme_042",
        "ability": "multi_session_reasoning",
        "question": "What video output specification must Benjamin Thorne's desk docking hub provide to run his workstation screens?",
        "subject": "Benjamin Thorne",
        "gold_answer": "Dual 4K DisplayPort outputs",
        "is_answerable": True,
        "context_facts": [
            {
                "subject": "Benjamin Thorne",
                "relation": "monitor_setup",
                "fact": "[Session 1]: Benjamin Thorne uses twin 27-inch 4K UHD monitors wired via DisplayPort on his sit-stand desk.",
                "object": "twin 4K DisplayPort monitors"
            },
            {
                "subject": "Benjamin Thorne",
                "relation": "dock_requirement",
                "fact": "[Session 2]: Benjamin evaluated Thunderbolt 4 docking stations capable of driving dual 4K 60Hz DisplayPort signals simultaneously.",
                "object": "dual 4K DisplayPort outputs"
            }
        ]
    },

    # 5. Abstention (8 items, is_answerable=False, gold_answer="")
    {
        "id": "lme_043",
        "ability": "abstention",
        "question": "What is Alice Vance's ABO blood type?",
        "subject": "Alice Vance",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "Alice Vance",
                "relation": "prefers_beverage",
                "fact": "Alice Vance drinks loose-leaf Earl Grey tea every morning.",
                "object": "Earl Grey tea"
            },
            {
                "subject": "Alice Vance",
                "relation": "promoted_to",
                "fact": "Alice Vance serves as Engineering Manager for infrastructure.",
                "object": "Engineering Manager"
            }
        ]
    },
    {
        "id": "lme_044",
        "ability": "abstention",
        "question": "What was David Kim's cumulative high school grade point average?",
        "subject": "David Kim",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "David Kim",
                "relation": "codes_in",
                "fact": "David Kim specializes in high-throughput network daemons written in Rust.",
                "object": "Rust"
            },
            {
                "subject": "David Kim",
                "relation": "switched_to",
                "fact": "David Kim uses Neovim with custom Lua configurations as his editor.",
                "object": "Neovim"
            }
        ]
    },
    {
        "id": "lme_045",
        "ability": "abstention",
        "question": "What is the maiden name of Elena Rostova's mother?",
        "subject": "Elena Rostova",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "Elena Rostova",
                "relation": "owns_pet",
                "fact": "Elena Rostova lives with her Golden Retriever named Apollo.",
                "object": "Golden Retriever"
            },
            {
                "subject": "Elena Rostova",
                "relation": "currently_drives",
                "fact": "Elena drives a Tesla Model Y electric crossover.",
                "object": "Tesla Model Y"
            }
        ]
    },
    {
        "id": "lme_046",
        "ability": "abstention",
        "question": "What is Marcus Chen's official passport identification number?",
        "subject": "Marcus Chen",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "Marcus Chen",
                "relation": "relocated_to",
                "fact": "Marcus Chen relocated to Zurich, Switzerland in August 2024.",
                "object": "Zurich"
            },
            {
                "subject": "Marcus Chen",
                "relation": "visited",
                "fact": "Marcus Chen visited Tokyo and Kyoto in autumn 2023.",
                "object": "Japan"
            }
        ]
    },
    {
        "id": "lme_047",
        "ability": "abstention",
        "question": "What is the WPA2 pre-shared Wi-Fi key for Priya Patel's home router?",
        "subject": "Priya Patel",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "Priya Patel",
                "relation": "graduated_from",
                "fact": "Priya Patel earned her PhD in Computer Science from Stanford University.",
                "object": "Stanford University"
            },
            {
                "subject": "Priya Patel",
                "relation": "current_employer",
                "fact": "Priya Patel joined Anthropic as a Member of Technical Staff in March 2024.",
                "object": "Anthropic"
            }
        ]
    },
    {
        "id": "lme_048",
        "ability": "abstention",
        "question": "What is the four-digit security PIN for Julian Weber's debit card?",
        "subject": "Julian Weber",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "Julian Weber",
                "relation": "uses_hardware",
                "fact": "Julian Weber built an 80% custom mechanical keyboard equipped with Cherry MX Brown switches.",
                "object": "Cherry MX Brown"
            },
            {
                "subject": "Julian Weber",
                "relation": "ran_marathon",
                "fact": "Julian Weber completed the Berlin Marathon in 3 hours 18 minutes.",
                "object": "Berlin Marathon"
            }
        ]
    },
    {
        "id": "lme_049",
        "ability": "abstention",
        "question": "What street address did Sarah Connor live at during her elementary school years?",
        "subject": "Sarah Connor",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "Sarah Connor",
                "relation": "plays_instrument",
                "fact": "Sarah Connor plays an American Professional II Fender Stratocaster.",
                "object": "Fender Stratocaster"
            },
            {
                "subject": "Sarah Connor",
                "relation": "current_os",
                "fact": "Sarah Connor runs NixOS on her primary ThinkPad workstation.",
                "object": "NixOS"
            }
        ]
    },
    {
        "id": "lme_050",
        "ability": "abstention",
        "question": "What is Benjamin Thorne's private SSH passphrase for his personal GitHub account?",
        "subject": "Benjamin Thorne",
        "gold_answer": "",
        "is_answerable": False,
        "context_facts": [
            {
                "subject": "Benjamin Thorne",
                "relation": "produces_podcast",
                "fact": "Benjamin Thorne produces a podcast titled The Distributed Ledger.",
                "object": "The Distributed Ledger"
            },
            {
                "subject": "Benjamin Thorne",
                "relation": "delivered_keynote",
                "fact": "Benjamin Thorne presented a keynote titled 'Zero-Cost Async Graphs' at RustConf.",
                "object": "RustConf"
            }
        ]
    }
]

# ---------------------------------------------------------
# 3. Kortext Golden Set (20 real codebase questions)
# ---------------------------------------------------------
kortext_golden_data = [
    {
        "id": "cg_001",
        "query": "Where is RetrievalEngine defined and what signals does it use?",
        "gold_passages": [
            "RetrievalEngine",
            "apply_taak_trimming",
            "W_AST",
            "W_DENSE"
        ],
        "notes": "Tests AST seek + RRF signal lookup"
    },
    {
        "id": "cg_002",
        "query": "How does SymbolSeekEngine look up symbols in FalkorDB without ripgrep?",
        "gold_passages": [
            "SymbolSeekEngine",
            "extract_symbol_candidates",
            "kortext_symbols",
            "STOP_WORDS"
        ],
        "notes": "Tests deterministic symbol seek mechanism and candidate extraction"
    },
    {
        "id": "cg_003",
        "query": "How is HippoRAG Personalized PageRank implemented for associative subgraph retrieval?",
        "gold_passages": [
            "HippoRAGPPR",
            "retrieve_associative_subgraph",
            "damping",
            "kortext_symbols"
        ],
        "notes": "Tests HippoRAG PPR power iteration and graph traversal"
    },
    {
        "id": "cg_004",
        "query": "What is the formula and parameters for the Stretched Weibull Decay Model and its biological floor?",
        "gold_passages": [
            "compute_weibull_retention",
            "lambda_h",
            "beta",
            "floor"
        ],
        "notes": "Tests mathematical formulation of episodic memory decay"
    },
    {
        "id": "cg_005",
        "query": "How does CausalSanitizer defend against MINJA adversarial prompt injections in persistent memory?",
        "gold_passages": [
            "CausalSanitizer",
            "SecurityViolation",
            "source_tier",
            "quarantine_dir"
        ],
        "notes": "Tests MINJA security defense and Tier 3 privilege isolation"
    },
    {
        "id": "cg_006",
        "query": "How does TaskDAGTracker manage topological task state and dependency transitions?",
        "gold_passages": [
            "TaskDAGTracker",
            "get_ready_tasks",
            "update_task_status",
            "kortext_tasks"
        ],
        "notes": "Tests Task DAG dependency resolution and state retention"
    },
    {
        "id": "cg_007",
        "query": "How does EmbeddedQdrantEngine initialize local vector storage and handle vector point queries?",
        "gold_passages": [
            "EmbeddedQdrantEngine",
            "query_points",
            "DEFAULT_QDRANT_PATH",
            "text-dense"
        ],
        "notes": "Tests embedded Qdrant vector retrieval engine"
    },
    {
        "id": "cg_008",
        "query": "How does SymbolGraphManager trace blast radiuses and upstream/downstream symbol impacts?",
        "gold_passages": [
            "SymbolGraphManager",
            "trace_symbol_impact",
            "max_depth",
            "upstream"
        ],
        "notes": "Tests graph blast radius calculation and impact analysis"
    },
    {
        "id": "cg_009",
        "query": "What algorithm does LouvainCommunityClusterer use to cluster code symbols into architectural communities?",
        "gold_passages": [
            "LouvainCommunityClusterer",
            "detect_communities",
            "modularity",
            "resolution"
        ],
        "notes": "Tests community detection and code clustering"
    },
    {
        "id": "cg_010",
        "query": "What occurs during Cognitive Dream Mode consolidation in kortext.dream?",
        "gold_passages": [
            "DreamConsolidator",
            "trigger_dream_mode",
            "prune_weak_edges",
            "consolidate"
        ],
        "notes": "Tests episodic dream consolidation and memory pruning"
    },
    {
        "id": "cg_011",
        "query": "How does HandoffEngine persist and compact context across agent sessions?",
        "gold_passages": [
            "HandoffEngine",
            "memory_session_handoff",
            "compact_context",
            "episodic"
        ],
        "notes": "Tests session handoff continuity and memory transition"
    },
    {
        "id": "cg_012",
        "query": "What substrate services are verified in check_kortext_health?",
        "gold_passages": [
            "audit_kortext_health",
            "check_kortext_health",
            "check_falkordb",
            "check_qdrant"
        ],
        "notes": "Tests health monitoring across FalkorDB, Qdrant, and embedding endpoints"
    },
    {
        "id": "cg_013",
        "query": "How does Kortext server register and dispatch FastMCP tools?",
        "gold_passages": [
            "check_kortext_health",
            "search_knowledge_and_memory",
            "seek_symbol",
            "manage_tasks"
        ],
        "notes": "Tests FastMCP server tool exposure and dispatch"
    },
    {
        "id": "cg_014",
        "query": "What physics solver and hard-freeze invariant does the dashboard use for graph stability?",
        "gold_passages": [
            "barnesHut",
            "gravitationalConstant",
            "stabilizationIterationsDone",
            "physics: { enabled: false }"
        ],
        "notes": "Tests dashboard physics configuration and stabilization freeze invariant"
    },
    {
        "id": "cg_015",
        "query": "How does Truncation-Aware Adaptive Knee (TAA-k) trimming determine the cutoff threshold for retrieved candidates?",
        "gold_passages": [
            "apply_taak_trimming",
            "k_min",
            "k_max",
            "scored_candidates"
        ],
        "notes": "Tests TAA-k adaptive trimming curvature logic"
    },
    {
        "id": "cg_016",
        "query": "How does EpisodicDriver record episodic events with bi-temporal validity?",
        "gold_passages": [
            "EpisodicDriver",
            "record_episode",
            "valid_from",
            "valid_to"
        ],
        "notes": "Tests bi-temporal episodic memory logging and validity windows"
    },
    {
        "id": "cg_017",
        "query": "How does SCIPExtractor parse SCIP indexer protobufs into symbol occurrences?",
        "gold_passages": [
            "SCIPExtractor",
            "Index",
            "Occurrence",
            "SymbolRole"
        ],
        "notes": "Tests SCIP protobuf parsing and symbol occurrence indexing"
    },
    {
        "id": "cg_018",
        "query": "How does MarkdownExtractor extract section hierarchies and code blocks into symbol graph nodes?",
        "gold_passages": [
            "MarkdownExtractor",
            "extract_headings",
            "code_blocks",
            "SymbolNode"
        ],
        "notes": "Tests markdown structural extraction for documentation graphs"
    },
    {
        "id": "cg_019",
        "query": "What system invariants are validated by InvariantChecker in kortext.invariants?",
        "gold_passages": [
            "InvariantChecker",
            "check_graph_integrity",
            "check_socket_permissions",
            "SoleCustodian"
        ],
        "notes": "Tests architectural invariant verification and system integrity"
    },
    {
        "id": "cg_020",
        "query": "How does get_shared_falkordb_client achieve connection resilience using Unix domain sockets and TCP fallback?",
        "gold_passages": [
            "get_shared_falkordb_client",
            "unix_socket_path",
            "falkordb.sock",
            "fallback_tcp_port"
        ],
        "notes": "Tests FalkorDB client socket connection and TCP failover resilience"
    }
]

def main():
    p_hotpot = FIXTURES_DIR / "hotpotqa_sample.json"
    p_longmem = FIXTURES_DIR / "longmemeval_sample.json"
    p_golden = FIXTURES_DIR / "kortext_golden_set.json"

    print(f"Writing {len(hotpotqa_data)} items to {p_hotpot}...")
    with open(p_hotpot, "w", encoding="utf-8") as f:
        json.dump(hotpotqa_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Writing {len(longmemeval_data)} items to {p_longmem}...")
    with open(p_longmem, "w", encoding="utf-8") as f:
        json.dump(longmemeval_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Writing {len(kortext_golden_data)} items to {p_golden}...")
    with open(p_golden, "w", encoding="utf-8") as f:
        json.dump(kortext_golden_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("All fixtures generated successfully!")

if __name__ == "__main__":
    main()
