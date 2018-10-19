import re


class Container:
    def __init__(self):
        self.mappings = {}
        self.registrations = {}
        self.strategies = []

    @staticmethod
    def constructor_args(t):
        return t.__init__.__code__.co_varnames[1:]

    @staticmethod
    def type_to_parameter_name(t):
        return re.sub('[a-z][A-Z]', lambda x: x.group()[:1] + '_' + x.group()[1:],
                      t.__name__).lower()

    def register_type(self, type_to_register, **registration):
        self.mappings[self.type_to_parameter_name(type_to_register)] = type_to_register
        self.registrations[type_to_register] = registration

    def register_types(self, *args):
        for arg in args:
            self.register_type(arg)

    def add_strategy(self, strategy):
        self.strategies.append(strategy)

    def add_strategies(self, *strategies):
        for strategy in strategies:
            self.add_strategy(strategy)

    def resolve_parameters(self, type_to_resolve, partial, **overridden_args):
        parameter_names = self.constructor_args(type_to_resolve)
        parameter_count = len(parameter_names) - 2 if partial else len(parameter_names)
        parameters = [None] * parameter_count
        registration = self.registrations.get(type_to_resolve)

        for index in range(parameter_count):
            parameter = None
            parameter_name = parameter_names[index]

            if parameter_name in overridden_args:
                parameter = overridden_args[parameter_name]
            else:
                for strategy in self.strategies:
                    parameter = strategy(type_to_resolve, parameter_names[index])
                    if parameter:
                        break

                if not parameter:
                    mapped_type = self.mappings.get(parameter_name)

                    if mapped_type:
                        parameter = self.resolve(mapped_type)
                    else:
                        assert registration,\
                            '%s not registered, parameter=%s' % (type_to_resolve, parameter_name)
                        assert parameter_name in registration,\
                            'parameter %s is not present in %s registration' % (parameter_name, type_to_resolve)
                        resolver = registration[parameter_name]
                        if type(resolver).__name__ == 'function':
                            parameter = registration[parameter_name](type_to_resolve, parameter_name)
                        else:
                            parameter = resolver

            parameters[index] = parameter
        return parameters

    def resolve(self, type_to_resolve, **overridden_args):
        return type_to_resolve(*self.resolve_parameters(type_to_resolve, False, **overridden_args))

    def resolve_partial(self, type_to_resolve, **overridden_args):
        resolved_parameters = self.resolve_parameters(type_to_resolve,
                                                      True, **overridden_args)

        class Partial(type_to_resolve):
            def __init__(self, *args, **kwargs):
                super(Partial, self).__init__(
                    *tuple(resolved_parameters + list(args)), **kwargs)

        return Partial
