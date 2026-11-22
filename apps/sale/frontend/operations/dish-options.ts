declare module '../operations' {
  interface ComboChoiceIn {
    /** The options of Modifiers chosen for the dish, in the order chosen (SALE-F42). */
    option_ids?: string[];
  }

  interface ComboDishOut {
    /** The options of Modifiers chosen for it, by name. */
    modifiers: string[];
  }

  interface SaleDishOut {
    /** The options charged inside it, by name. */
    modifiers: string[];
  }
}

export {};
