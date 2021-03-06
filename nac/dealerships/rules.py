

from django.core.exceptions import ObjectDoesNotExist
import rules


@rules.predicates.predicate
def is_dealership_principal(user, dealership):
    """
    Is the user a principal of a given dealership?
    """

    try:
        if user.dealershipuser is None: return False
        return user.dealershipuser.is_dealership_principal(dealership.id)
    except ObjectDoesNotExist:
        return False


@rules.predicates.predicate
def is_dealership_rep(user, dealership):
    """
    Is the user a rep of a given dealership?
    """
    if user.dealershipuser is None: return False
    return dealership.id in user.dealershipuser.get_dealership_ids()


rules.add_rule('dealership.is_principal', is_dealership_principal)
rules.add_rule('dealership.is_rep', is_dealership_rep)
