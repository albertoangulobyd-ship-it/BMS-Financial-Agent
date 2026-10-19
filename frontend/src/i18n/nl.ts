// Los textos de la app en neerlandes (el idioma por defecto). La forma de este objeto
// es el tipo `Messages`: en.ts tiene que tener exactamente las mismas claves (lo exige
// TypeScript y lo vuelve a mirar i18n.test.ts). Un {nombre} es un hueco que rellena fmt().
// Los textos de dominio (reglas, estados, prioridades) no van aqui: van en los catalogos
// de Python (i18n/domain.ts).

export const nl = {
  app: {
    name: 'BMS Finance',
    company: 'BM Support BV',
    testDataTitle: 'TESTGEGEVENS',
  },
  common: {
    loading: 'Laden…',
    retry: 'Opnieuw proberen',
    reload: 'Opnieuw laden',
    open: 'Openen',
    close: 'Sluiten',
    noData: 'Geen gegevens',
    unknown: 'Onbekend',
    comingSoon: 'Dit scherm wordt in de volgende versie gebouwd.',
    ruleCode: 'Regel {code}',
    details: 'Details',
    showDetails: 'Details tonen',
    hideDetails: 'Details verbergen',
  },
  units: {
    hoursShort: 'u',
  },
  months: {
    short: ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'],
    long: [
      'januari', 'februari', 'maart', 'april', 'mei', 'juni',
      'juli', 'augustus', 'september', 'oktober', 'november', 'december',
    ],
    weekdays: ['zondag', 'maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag'],
  },
  language: {
    label: 'Taal',
    nl: 'NL',
    en: 'EN',
    nlLong: 'Nederlands',
    enLong: 'English',
  },
  login: {
    title: 'Inloggen',
    intro: 'De financiële werkplek van BM Support BV.',
    tokenLabel: 'Persoonlijke code',
    tokenHelp:
      'Je persoonlijke code is een lange reeks tekens die je van de beheerder van het programma krijgt. Hij is alleen van jou: geef hem aan niemand.',
    submit: 'Inloggen',
    checking: 'Controleren…',
    empty: 'Vul je persoonlijke code in.',
    invalid: 'Deze code is niet geldig. Controleer hem of vraag de beheerder om een nieuwe.',
    forbidden: 'Met deze code mag je de facturen niet bekijken. Vraag de beheerder om toegang.',
    unreachable: 'Het programma reageert niet. Start het opnieuw met iniciar.bat en probeer het daarna nog eens.',
    incompatible: 'Deze app past niet bij de versie van het programma. Vraag de beheerder om het bij te werken.',
    sessionEnded: 'Je sessie is beëindigd. Log opnieuw in.',
    loggedOut: 'Je bent uitgelogd.',
    neverStored: 'De code blijft alleen in dit venster en verdwijnt bij uitloggen of sluiten.',
  },
  account: {
    menu: 'Accountmenu van {name}',
    signedInAs: 'Ingelogd als',
    roleAdmin: 'Beheerder',
    roleStaff: 'Administratie',
    roleReadOnly: 'Alleen lezen',
    logout: 'Uitloggen',
  },
  testData: {
    chip: 'Testgegevens',
    chipHelp: 'Dit is de testdatabase. Alles wat je ziet is verzonnen en niets gaat naar de echte gegevens.',
  },
  tabs: {
    newTab: 'Nieuw tabblad',
    closeTab: 'Tabblad sluiten',
    closeOtherTabs: 'Andere tabbladen sluiten',
    closeTabsToRight: 'Tabbladen rechts sluiten',
    closeTabsToLeft: 'Tabbladen links sluiten',
    closeAllTabs: 'Alle tabbladen sluiten',
    quickOpen: 'Snel openen',
    sidebarNavigation: 'Navigatie',
    collapseSidebar: 'Zijbalk inklappen',
    expandSidebar: 'Zijbalk uitklappen',
    moreTabOptions: 'Meer opties voor tabbladen',
    openMenu: 'Menu openen',
    close: 'Sluiten',
    tabs: 'Tabbladen',
    mainNavigation: 'Hoofdmenu',
  },
  groups: {
    daily: 'Dagelijks',
    invoices: 'Facturen',
    parties: 'Relaties',
    money: 'Geld',
    data: 'Gegevens',
    settings: '',
  },
  nav: {
    overview: {
      label: 'Overzicht',
      hint: '',
      description: 'Wat vandaag aandacht nodig heeft en hoe het geld ervoor staat.',
    },
    'work-queue': {
      label: 'Werklijst',
      hint: '',
      description: 'Alle facturen, met bovenaan wat het eerst moet.',
    },
    exceptions: {
      label: 'Uitzonderingen',
      hint: '',
      description: 'Open zaken die iemand moet oplossen, en wie ermee bezig is.',
    },
    'iban-checks': {
      label: 'IBAN-controles',
      hint: '',
      description: 'Bankrekeningen die nog telefonisch gecontroleerd moeten worden.',
    },
    'invoices-in': {
      label: 'Inkomend',
      hint: 'inkoop',
      description: 'Facturen van leveranciers en zzp’ers aan BMS.',
    },
    'invoices-out': {
      label: 'Uitgaand',
      hint: 'verkoop',
      description: 'Facturen van BMS aan klanten.',
    },
    providers: {
      label: 'Leveranciers',
      hint: '',
      description: 'Zzp’ers en onderaannemers: wat openstaat en wat opvalt.',
    },
    clients: {
      label: 'Klanten',
      hint: '',
      description: 'Wat klanten nog moeten betalen en wat nog gefactureerd moet worden.',
    },
    objects: {
      label: 'Objecten',
      hint: '',
      description: 'Per locatie van een klant: opbrengst, kosten en marge.',
    },
    'purchase-orders': {
      label: 'Inkooporders',
      hint: '',
      description: 'Hoeveel er van elke inkooporder over is, en welke bijna op zijn.',
    },
    'cash-flow': {
      label: 'Kasstroom',
      hint: '',
      description: 'Wat er de komende weken binnenkomt en uitgaat.',
    },
    vat: {
      label: 'Btw',
      hint: '',
      description: 'De btw per kwartaal, klaar om te controleren. De aangifte doet een mens.',
    },
    import: {
      label: 'Importeren',
      hint: '',
      description: 'Bestanden uit Exact, van de bank en uit TRNSPRNT inlezen.',
    },
    'read-invoices': {
      label: 'Facturen lezen',
      hint: 'kost geld',
      description: 'Pdf’s laten lezen. Je ziet eerst wat het kost.',
    },
    settings: {
      label: 'Instellingen',
      hint: '',
      description: 'Je taal en je account.',
    },
  },
  records: {
    invoice: { label: 'Factuur', fallbackTitle: 'Factuur {id}' },
    provider: { label: 'Leverancier', fallbackTitle: 'Leverancier {id}' },
    client: { label: 'Klant', fallbackTitle: 'Klant {id}' },
    object: { label: 'Object', fallbackTitle: 'Object {id}' },
    'purchase-order': { label: 'Inkooporder', fallbackTitle: 'Inkooporder {id}' },
  },
  badges: {
    blocked: 'geblokkeerd',
    open: 'open',
    toCheck: 'te controleren',
  },
  help: {
    object: {
      term: 'Object',
      text: 'Een locatie van een klant waar BMS mensen inzet, zoals een gebouw of terrein. TRNSPRNT gebruikt hetzelfde woord.',
    },
    po: {
      term: 'Inkooporder',
      text: 'Een inkooporder (PO) is een afspraak over hoeveel er maximaal gefactureerd mag worden. Een klant geeft er een aan BMS, of BMS aan een leverancier.',
    },
    btw: {
      term: 'Btw',
      text: 'De belasting op de omzet. BMS doet elk kwartaal aangifte bij de Belastingdienst; dit programma maakt alleen het werkblad.',
    },
    exception: {
      term: 'Uitzondering',
      text: 'Een zaak die niet vanzelf goed komt en die iemand moet oplossen, bijvoorbeeld een factuur die twee keer binnenkwam.',
    },
    whatIs: 'Wat is {term}?',
  },
  priority: {
    column: 'Prioriteit',
  },
  errors: {
    title: 'Dit lukt nu niet',
    unauthorized: 'Je sessie is beëindigd. Log opnieuw in.',
    forbidden: 'Je hebt geen toestemming hiervoor.',
    notFound: 'Dit bestaat niet (meer).',
    stale: 'Iemand anders heeft dit net gewijzigd. Laad opnieuw om de nieuwste versie te zien.',
    conflict: 'Dit kan nu niet, door de huidige stand van zaken.',
    badRequest: 'De gegevens zijn niet geaccepteerd. Controleer wat je hebt ingevuld.',
    unavailable: 'Het programma reageert niet. Probeer het zo nog eens.',
    incompatible: 'Deze app past niet bij de versie van het programma.',
    unexpected: 'Er ging iets mis. Probeer het opnieuw.',
  },
  empty: {
    nothingNeedsAttention: 'Niets heeft je aandacht nodig',
    nothingHere: 'Hier staat nog niets',
  },
  footer: {
    today: 'Vandaag',
  },
  workQueue: {
    columns: {
      number: 'Nummer',
      party: 'Relatie',
      amount: 'Bedrag',
      due: 'Vervaldatum',
      payment: 'Betaling',
    },
    caption: 'Facturen, met bovenaan wat het eerst moet',
    baseNote: 'Basisversie: de kolom “Waarom” komt erbij zodra de teksten van de regels er zijn.',
    empty: 'Er zijn nog geen facturen.',
    total: '{count} facturen',
  },
  invoice: {
    baseNote: 'Wat er mis is en wat je moet doen, komt in de volgende versie op dit scherm.',
    partyLabel: 'Relatie',
    totalLabel: 'Totaal',
    dateLabel: 'Factuurdatum',
    dueLabel: 'Vervaldatum',
  },
  settings: {
    languageHelp: 'De taal van de app. Bedragen en datums blijven altijd in Nederlandse notatie.',
    accountHelp: 'Je bent ingelogd met je persoonlijke code. Uitloggen wist de code uit dit venster.',
  },
};
