window.servicesData = {
  serviceGroups: [
    { id: 1, name: "Анализы", sortOrder: 10, isActive: true },
    { id: 2, name: "ВУ", sortOrder: 20, isActive: true },
    { id: 3, name: "ГИМС", sortOrder: 30, isActive: true },
    { id: 4, name: "ЛМК", sortOrder: 40, isActive: true },
    { id: 5, name: "Приём врачей", sortOrder: 50, isActive: true },
    { id: 6, name: "Профосмотры", sortOrder: 60, isActive: true },
    { id: 7, name: "Справки", sortOrder: 70, isActive: true },
    { id: 8, name: "УЗИ", sortOrder: 80, isActive: true },
    { id: 9, name: "ЭКГ", sortOrder: 90, isActive: true }
  ],

  doctorRoles: [
    { id: 1, name: "Терапевт", sortOrder: 10, isActive: true },
    { id: 2, name: "Психиатр", sortOrder: 20, isActive: true },
    { id: 3, name: "Психиатр-Нарколог", sortOrder: 30, isActive: true },
    { id: 4, name: "Невролог", sortOrder: 40, isActive: true },
    { id: 5, name: "Отоларинголог", sortOrder: 50, isActive: true },
    { id: 6, name: "Гинеколог", sortOrder: 60, isActive: true },
    { id: 7, name: "Офтальмолог", sortOrder: 70, isActive: true },
    { id: 8, name: "Дерматовенеролог", sortOrder: 80, isActive: true },
    { id: 9, name: "Стоматолог", sortOrder: 90, isActive: true },
    { id: 10, name: "Хирург", sortOrder: 100, isActive: true },
    { id: 11, name: "Фтизиатр", sortOrder: 110, isActive: true },
    { id: 12, name: "Узист", sortOrder: 120, isActive: true },
    { id: 13, name: "Председатель", sortOrder: 130, isActive: true }
  ],

  services: [
    {
      id: 22,
      name: "Анализы",
      groupId: 1,
      price: 1000,
      notes: "",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: []
    },

    {
      id: 8,
      name: "Водительская справка",
      groupId: 2,
      price: 4000,
      notes: "ВОДИЛКА 4000",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: []
    },
    {
      id: 29,
      name: "Водительская справка",
      groupId: 2,
      price: 3500,
      notes: "ВОДИЛКА 3500",
      isActive: true,
      sortOrder: 20,
      doctorRoleIds: []
    },
    {
      id: 7,
      name: "071У",
      groupId: 2,
      price: 4000,
      notes: "",
      isActive: true,
      sortOrder: 30,
      doctorRoleIds: []
    },

    {
      id: 37,
      name: "ГИМС",
      groupId: 3,
      price: 3500,
      notes: "ГИМС",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: []
    },

    {
      id: 18,
      name: "ЛМК",
      groupId: 4,
      price: 4000,
      notes: "",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: []
    },
    {
      id: 33,
      name: "Направление на Флюорографию",
      groupId: 4,
      price: 1000,
      notes: "",
      isActive: true,
      sortOrder: 20,
      doctorRoleIds: []
    },
    {
      id: 19,
      name: "Продление ЛМК",
      groupId: 4,
      price: 3500,
      notes: "",
      isActive: true,
      sortOrder: 30,
      doctorRoleIds: []
    },
    {
      id: 23,
      name: "ФОТО для ЛМК",
      groupId: 4,
      price: 200,
      notes: "",
      isActive: true,
      sortOrder: 40,
      doctorRoleIds: []
    },

    {
      id: 35,
      name: "Повторный приём врача НЕВРОЛОГА",
      groupId: 5,
      price: 1800,
      notes: "",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: [4]
    },
    {
      id: 34,
      name: "Приём врача НЕВРОЛОГА",
      groupId: 5,
      price: 2200,
      notes: "",
      isActive: true,
      sortOrder: 30,
      doctorRoleIds: [4]
    },
    {
      id: 28,
      name: "Приём врача ТЕРАПЕВТА",
      groupId: 5,
      price: 2200,
      notes: "",
      isActive: true,
      sortOrder: 40,
      doctorRoleIds: [1]
    },

    {
      id: 16,
      name: "Первичный профосмотр 29Н",
      groupId: 6,
      price: 3500,
      notes: "",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    },

    {
      id: 24,
      name: "Санаторно-курортная карта 072У",
      groupId: 7,
      price: 2500,
      notes: "",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: [1, 13]
    },
    {
      id: 2,
      name: "Справка формы 001 ГСУ",
      groupId: 7,
      price: 1800,
      notes: "",
      isActive: true,
      sortOrder: 20,
      doctorRoleIds: [1, 2, 3, 13]
    },
    {
      id: 9,
      name: "Справка 002 ЧОД (для охраны)",
      groupId: 7,
      price: 3500,
      notes: "",
      isActive: true,
      sortOrder: 30,
      doctorRoleIds: [13]
    },
    {
      id: 3,
      name: "Справка для посещения бассейна",
      groupId: 7,
      price: 1000,
      notes: "",
      isActive: true,
      sortOrder: 40,
      doctorRoleIds: [1, 13]
    },
    {
      id: 10,
      name: "Справка выезжающих за границу 082у",
      groupId: 7,
      price: 2000,
      notes: "",
      isActive: true,
      sortOrder: 50,
      doctorRoleIds: [13]
    },
    {
      id: 11,
      name: "Справка для работы с гостайной формы 989Н",
      groupId: 7,
      price: 1800,
      notes: "",
      isActive: true,
      sortOrder: 60,
      doctorRoleIds: [1, 2, 3, 4, 13]
    },
    {
      id: 4,
      name: "Справка ГТО 1144",
      groupId: 7,
      price: 1500,
      notes: "",
      isActive: true,
      sortOrder: 70,
      doctorRoleIds: [1, 13]
    },
    {
      id: 12,
      name: "Справка формы 086у",
      groupId: 7,
      price: 2200,
      notes: "",
      isActive: true,
      sortOrder: 80,
      doctorRoleIds: [1, 13]
    },
    {
      id: 30,
      name: "095",
      groupId: 7,
      price: 1800,
      notes: "",
      isActive: true,
      sortOrder: 90,
      doctorRoleIds: [1, 13]
    },
    {
      id: 5,
      name: "спорт",
      groupId: 7,
      price: 1200,
      notes: "",
      isActive: true,
      sortOrder: 100,
      doctorRoleIds: [1, 13]
    },

    {
      id: 13,
      name: "УЗИ брюшной полости",
      groupId: 8,
      price: 2000,
      notes: "",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: []
    },
    {
      id: 14,
      name: "УЗИ молочных желез",
      groupId: 8,
      price: 1500,
      notes: "",
      isActive: true,
      sortOrder: 20,
      doctorRoleIds: []
    },
    {
      id: 15,
      name: "УЗИ предстательной железы",
      groupId: 8,
      price: 1500,
      notes: "",
      isActive: true,
      sortOrder: 30,
      doctorRoleIds: []
    },

    {
      id: 20,
      name: "ЭКГ без расшифровки",
      groupId: 9,
      price: 700,
      notes: "",
      isActive: true,
      sortOrder: 10,
      doctorRoleIds: []
    },
    {
      id: 21,
      name: "ЭКГ при нагрузке с расшифровкой",
      groupId: 9,
      price: 1700,
      notes: "",
      isActive: true,
      sortOrder: 20,
      doctorRoleIds: []
    },
    {
      id: 6,
      name: "ЭКГ с расшифровкой",
      groupId: 9,
      price: 1200,
      notes: "",
      isActive: true,
      sortOrder: 30,
      doctorRoleIds: []
    }
  ]
};
