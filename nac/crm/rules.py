

import rules


@rules.predicates.predicate
def manage_all_leads(user, obj):
    if user.has_perm('customers.list_customer'):
        if not user.has_perm('customers.manage_self_and_dealership_leads_only'):
            return True

    return False

@rules.predicates.predicate
def broadcast_email_to_all_leads(user, obj):
    if user.has_perm('customers.broadcast_email'):
        if not user.has_perm('customers.email_broadcast_self_and_dealership_leads_only'):
            return True

    return False

rules.add_perm('crm.manage_all_leads', manage_all_leads)
rules.add_perm('crm.broadcast_email_to_all_leads', broadcast_email_to_all_leads)
